from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from html import escape

from flask import current_app
from sqlalchemy import func

from models import (
    AbnormalEvent,
    BowelRecord,
    Elder,
    MedRecord,
    MealRecord,
    Photo,
    Setting,
    VitalRecord,
    WaterRecord,
    db,
    get_care_parameters,
    get_setting,
    log_action,
)
from services.mailer import MailNotConfigured, send_mail
from services.media import active_photos_query
from translations import tr, tr_format


CATEGORY_LABELS = {
    "health": "健康數據",
    "medication": "用藥",
    "nutrition": "進食",
    "bowel": "排便",
    "hydration": "飲水",
}

EVENT_TYPE_LABELS = {
    "systolic_high": "收縮壓偏高",
    "systolic_low": "收縮壓偏低",
    "diastolic_high": "舒張壓偏高",
    "diastolic_low": "舒張壓偏低",
    "pulse_high": "脈搏偏高",
    "pulse_low": "脈搏偏低",
    "spo2_low": "血氧偏低",
    "med_not_given": "未給藥",
    "bowel_abnormal": "排便型態異常",
    "meal_none": "未進食",
    "meal_little": "進食量偏少",
    "water_low": "每日飲水不足",
}

STATUS_LABELS = {
    "pending": "待確認",
    "tracking": "追蹤中",
    "resolved": "已解除",
    "dismissed": "排除",
}

SEVERITY_LABELS = {
    "attention": "注意",
    "warning": "警告",
    "critical": "嚴重",
}


@dataclass
class EventSpec:
    event_key: str
    category: str
    event_type: str
    metric_code: str | None = None
    direction: str | None = None
    observed_value: float | None = None
    observed_text: str | None = None
    unit: str | None = None
    threshold_operator: str | None = None
    threshold_value: float | None = None
    threshold_snapshot: dict | None = None
    severity: str = "warning"


def abnormal_rules() -> dict:
    params = get_care_parameters()
    rules = dict(params.get("abnormal_rules") or {})
    # Databases upgraded from 1.1 may have customised thresholds in the old key.
    legacy = get_setting("thresholds") or {}
    care_row = db.session.get(Setting, "care_parameters")
    if legacy and care_row is None:
        rules["vitals_enabled"] = legacy.get("enabled", True)
        for key in (
            "sys_hi",
            "sys_lo",
            "dia_hi",
            "dia_lo",
            "pulse_hi",
            "pulse_lo",
            "spo2_lo",
        ):
            if key in legacy:
                rules[key] = legacy[key]
    return rules


def _severity_for_vital(metric: str, value: float, direction: str) -> str:
    if metric == "spo2" and value <= 88:
        return "critical"
    if metric == "systolic" and (
        (direction == "high" and value >= 180)
        or (direction == "low" and value <= 80)
    ):
        return "critical"
    return "warning"


def _upsert_event(
    *,
    elder_id: int,
    occurred_at: datetime,
    source_type: str,
    source_id: int,
    created_by: int | None,
    spec: EventSpec,
) -> tuple[AbnormalEvent, bool]:
    event = AbnormalEvent.query.filter_by(event_key=spec.event_key).first()
    created = event is None
    if event is None:
        event = AbnormalEvent(
            event_key=spec.event_key,
            elder_id=elder_id,
            occurred_at=occurred_at,
            detected_at=datetime.now(),
            source_type=source_type,
            source_id=source_id,
            created_by=created_by,
            status="pending",
            notification_status="not_requested",
        )
        db.session.add(event)
    event.category = spec.category
    event.event_type = spec.event_type
    event.metric_code = spec.metric_code
    event.direction = spec.direction
    event.observed_value = spec.observed_value
    event.observed_text = spec.observed_text
    event.unit = spec.unit
    event.threshold_operator = spec.threshold_operator
    event.threshold_value = spec.threshold_value
    event.threshold_snapshot = json.dumps(
        spec.threshold_snapshot or {}, ensure_ascii=False, default=str
    )
    event.severity = spec.severity
    if event.status in ("resolved", "dismissed") and not created:
        # A changed source value can make a previously closed condition active again.
        event.status = "pending"
        event.resolved_by = None
        event.resolved_at = None
    db.session.flush()
    return event, created


def _mark_obsolete(source_type: str, source_id: int, active_keys: set[str]) -> None:
    existing = AbnormalEvent.query.filter_by(
        source_type=source_type, source_id=source_id
    ).all()
    for event in existing:
        if event.event_key not in active_keys and event.status not in (
            "resolved",
            "dismissed",
        ):
            event.status = "dismissed"
            event.resolved_at = datetime.now()
            note = "原始紀錄修改後已不再符合異常條件。"
            event.handling_note = (
                f"{event.handling_note}\n{note}".strip()
                if event.handling_note
                else note
            )


def _source_photos(event: AbnormalEvent) -> list[Photo]:
    query = active_photos_query()
    photos: list[Photo] = []
    if event.source_type in ("meal", "vital", "bowel"):
        photos.extend(
            query.filter_by(
                record_type=event.source_type,
                record_id=event.source_id,
                kind="care_evidence",
            ).all()
        )
    elif event.source_type == "med":
        record = db.session.get(MedRecord, event.source_id)
        if record:
            # CareLog 1.1 attached a submission photo directly to the first
            # medication record. Keep those legacy photos visible after upgrade.
            photos.extend(
                query.filter_by(
                    record_type="med",
                    record_id=record.id,
                    kind="care_evidence",
                ).all()
            )
            if record.submission_id:
                photos.extend(
                    query.filter_by(
                        record_type="med_submission",
                        record_id=record.submission_id,
                        kind="care_evidence",
                    ).all()
                )
            photos.extend(
                query.filter_by(
                    record_type="medplan",
                    record_id=record.med_plan_id,
                    kind="med_reference",
                ).all()
            )
    # Follow-up images are always linked directly by the upload route.
    seen = set()
    unique = []
    for photo in photos:
        if photo.id not in seen:
            seen.add(photo.id)
            unique.append(photo)
    return unique


def link_event_photos(event: AbnormalEvent) -> None:
    existing = {photo.id: photo for photo in event.photos if photo.deleted_at is None}
    for photo in _source_photos(event):
        existing[photo.id] = photo
    event.photos = list(existing.values())


def _notify_vital_events(elder: Elder, events: list[AbnormalEvent]) -> None:
    if not events:
        return
    items = []
    for event in events:
        label = EVENT_TYPE_LABELS.get(event.event_type, event.event_type)
        value = (
            f"{event.observed_value:g}{event.unit or ''}"
            if event.observed_value is not None
            else event.observed_text or "—"
        )
        threshold = ""
        if event.threshold_operator and event.threshold_value is not None:
            threshold = f"（警戒值 {event.threshold_operator} {event.threshold_value:g}）"
        items.append(f"<li>{escape(label)}：{escape(value)} {escape(threshold)}</li>")
    html = f"""
    <div style="font-family:'Noto Sans TC',sans-serif;max-width:560px;margin:auto;">
      <div style="background:#C4534A;color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;
                  font-size:17px;font-weight:700;">⚠️ 健康數據異常警示</div>
      <div style="border:1px solid #eadcda;border-top:none;padding:18px;border-radius:0 0 10px 10px;">
        <p>長輩 <b>{escape(elder.name)}</b> 的量測數據超出警戒範圍：</p>
        <ul>{''.join(items)}</ul>
        <p style="color:#6b7a76;font-size:13px;">異常事件已保存在 CareLog 後台，請確認長輩狀況並留下處理紀錄。</p>
      </div>
    </div>"""
    try:
        for event in events:
            event.notification_status = "sending"
        db.session.commit()
        send_mail(f"⚠️ 異常警示：{elder.name} 健康數據超標", html)
        for event in events:
            event.notification_status = "sent"
    except MailNotConfigured:
        for event in events:
            event.notification_status = "mail_not_configured"
    except Exception:
        current_app.logger.exception("Abnormal-vital alert email failed")
        for event in events:
            event.notification_status = "failed"
    db.session.commit()


def evaluate_vital(
    elder: Elder,
    vital: VitalRecord,
    *,
    lang: str = "zh",
    send_notification: bool = True,
) -> list[str]:
    rules = abnormal_rules()
    specs: list[EventSpec] = []

    def check(value, metric, hi_key, lo_key, unit):
        if value is None:
            return
        hi = rules.get(hi_key)
        lo = rules.get(lo_key)
        if hi is not None and value >= hi:
            specs.append(
                EventSpec(
                    event_key=f"vital:{vital.id}:{metric}:high",
                    category="health",
                    event_type=f"{metric}_high",
                    metric_code=metric,
                    direction="high",
                    observed_value=value,
                    unit=unit,
                    threshold_operator="≥",
                    threshold_value=hi,
                    threshold_snapshot=dict(rules),
                    severity=_severity_for_vital(metric, value, "high"),
                )
            )
        elif lo is not None and value <= lo:
            specs.append(
                EventSpec(
                    event_key=f"vital:{vital.id}:{metric}:low",
                    category="health",
                    event_type=f"{metric}_low",
                    metric_code=metric,
                    direction="low",
                    observed_value=value,
                    unit=unit,
                    threshold_operator="≤",
                    threshold_value=lo,
                    threshold_snapshot=dict(rules),
                    severity=_severity_for_vital(metric, value, "low"),
                )
            )

    if rules.get("vitals_enabled", True):
        check(vital.systolic, "systolic", "sys_hi", "sys_lo", " mmHg")
        check(vital.diastolic, "diastolic", "dia_hi", "dia_lo", " mmHg")
        check(vital.pulse, "pulse", "pulse_hi", "pulse_lo", " bpm")
        spo2_limit = rules.get("spo2_lo")
        if vital.spo2 is not None and spo2_limit is not None and vital.spo2 <= spo2_limit:
            specs.append(
                EventSpec(
                    event_key=f"vital:{vital.id}:spo2:low",
                    category="health",
                    event_type="spo2_low",
                    metric_code="spo2",
                    direction="low",
                    observed_value=vital.spo2,
                    unit="%",
                    threshold_operator="≤",
                    threshold_value=spo2_limit,
                    threshold_snapshot=dict(rules),
                    severity=_severity_for_vital("spo2", vital.spo2, "low"),
                )
            )

    active_keys = {spec.event_key for spec in specs}
    _mark_obsolete("vital", vital.id, active_keys)
    created_events: list[AbnormalEvent] = []
    all_events: list[AbnormalEvent] = []
    for spec in specs:
        event, created = _upsert_event(
            elder_id=elder.id,
            occurred_at=vital.recorded_at,
            source_type="vital",
            source_id=vital.id,
            created_by=vital.created_by,
            spec=spec,
        )
        link_event_photos(event)
        all_events.append(event)
        if created:
            created_events.append(event)
            log_action(
                vital.created_by,
                "create",
                "abnormal",
                event.id,
                EVENT_TYPE_LABELS.get(event.event_type, event.event_type),
                elder_id=elder.id,
                event_code="abnormal.detected",
                metadata={"source_type": "vital", "source_id": vital.id},
            )
    db.session.commit()
    if send_notification:
        _notify_vital_events(elder, created_events)

    label_keys = {
        "systolic": "systolic",
        "diastolic": "diastolic",
        "pulse": "pulse",
        "spo2": "spo2",
    }
    return [
        tr_format(
            lang,
            f"alert_{event.direction}",
            label=tr(lang, label_keys.get(event.metric_code, event.metric_code or "")),
            value=f"{event.observed_value:g}" if event.observed_value is not None else "",
            unit=event.unit or "",
            threshold=f"{event.threshold_value:g}"
            if event.threshold_value is not None
            else "",
        )
        for event in all_events
    ]


def evaluate_meal(record: MealRecord) -> list[AbnormalEvent]:
    rules = abnormal_rules()
    specs = []
    if record.intake == "none" and rules.get("meal_none_enabled", True):
        specs.append(
            EventSpec(
                event_key=f"meal:{record.id}:none",
                category="nutrition",
                event_type="meal_none",
                metric_code="intake",
                observed_text="未進食",
                threshold_snapshot={"intake": "none"},
                severity="warning",
            )
        )
    elif record.intake == "little" and rules.get("meal_little_enabled", False):
        specs.append(
            EventSpec(
                event_key=f"meal:{record.id}:little",
                category="nutrition",
                event_type="meal_little",
                metric_code="intake",
                observed_text="少量",
                threshold_snapshot={"intake": "little"},
                severity="attention",
            )
        )
    return _evaluate_simple(
        record, "meal", record.id, record.updated_at or record.created_at, specs
    )


def evaluate_bowel(record: BowelRecord) -> list[AbnormalEvent]:
    rules = abnormal_rules()
    abnormal_types = {int(value) for value in rules.get("bowel_types", [1, 2, 6, 7])}
    specs = []
    if rules.get("bowel_enabled", True) and record.bristol_type in abnormal_types:
        specs.append(
            EventSpec(
                event_key=f"bowel:{record.id}:bristol:{record.bristol_type}",
                category="bowel",
                event_type="bowel_abnormal",
                metric_code="bristol_type",
                observed_value=record.bristol_type,
                observed_text=f"Bristol {record.bristol_type}",
                threshold_snapshot={"abnormal_types": sorted(abnormal_types)},
                severity="attention",
            )
        )
    return _evaluate_simple(record, "bowel", record.id, record.recorded_at, specs)


def evaluate_med_records(records: list[MedRecord]) -> list[AbnormalEvent]:
    rules = abnormal_rules()
    all_events = []
    for record in records:
        specs = []
        if rules.get("med_not_given_enabled", True) and not record.given:
            specs.append(
                EventSpec(
                    event_key=f"med:{record.id}:not_given",
                    category="medication",
                    event_type="med_not_given",
                    metric_code="given",
                    observed_text=(
                        f"{record.plan.name}：{record.reason or '未填原因'}"
                        if record.plan
                        else record.reason or "未給藥"
                    ),
                    threshold_snapshot={"expected": "given"},
                    severity="warning",
                )
            )
        occurred = record.updated_at or record.created_at or datetime.now()
        all_events.extend(_evaluate_simple(record, "med", record.id, occurred, specs))
    return all_events


def _evaluate_simple(record, source_type, source_id, occurred_at, specs):
    active_keys = {spec.event_key for spec in specs}
    _mark_obsolete(source_type, source_id, active_keys)
    events = []
    for spec in specs:
        event, created = _upsert_event(
            elder_id=record.elder_id,
            occurred_at=occurred_at,
            source_type=source_type,
            source_id=source_id,
            created_by=record.created_by,
            spec=spec,
        )
        link_event_photos(event)
        events.append(event)
        if created:
            log_action(
                record.created_by,
                "create",
                "abnormal",
                event.id,
                EVENT_TYPE_LABELS.get(event.event_type, event.event_type),
                elder_id=record.elder_id,
                event_code="abnormal.detected",
                metadata={"source_type": source_type, "source_id": source_id},
            )
    db.session.commit()
    return events


def evaluate_daily_water(elder: Elder, record_day: date) -> AbnormalEvent | None:
    rules = abnormal_rules()
    event_key = f"water:{elder.id}:{record_day.isoformat()}:low"
    if not rules.get("water_low_enabled", False):
        existing = AbnormalEvent.query.filter_by(event_key=event_key).first()
        if existing and existing.status not in ("resolved", "dismissed"):
            existing.status = "dismissed"
            existing.resolved_at = datetime.now()
            db.session.commit()
        return None

    total = (
        db.session.query(func.coalesce(func.sum(WaterRecord.amount), 0))
        .filter_by(elder_id=elder.id, record_date=record_day)
        .scalar()
    )
    percent = max(1, int(rules.get("water_min_percent", 100)))
    threshold = round((elder.water_goal or 0) * percent / 100)
    if total >= threshold:
        existing = AbnormalEvent.query.filter_by(event_key=event_key).first()
        if existing and existing.status not in ("resolved", "dismissed"):
            existing.status = "resolved"
            existing.resolved_at = datetime.now()
            existing.handling_note = "當日飲水總量後續已達設定標準。"
            db.session.commit()
        return None

    spec = EventSpec(
        event_key=event_key,
        category="hydration",
        event_type="water_low",
        metric_code="water_daily",
        direction="low",
        observed_value=float(total),
        unit=" ml",
        threshold_operator="<",
        threshold_value=float(threshold),
        threshold_snapshot={
            "water_goal": elder.water_goal,
            "minimum_percent": percent,
        },
        severity="attention",
    )
    event, created = _upsert_event(
        elder_id=elder.id,
        occurred_at=datetime.combine(record_day, time(23, 59)),
        source_type="water_daily",
        source_id=int(record_day.strftime("%Y%m%d")),
        created_by=None,
        spec=spec,
    )
    if created:
        log_action(
            None,
            "create",
            "abnormal",
            event.id,
            EVENT_TYPE_LABELS["water_low"],
            elder_id=elder.id,
            event_code="abnormal.detected",
            metadata={"record_date": record_day.isoformat(), "water_total": total},
        )
    db.session.commit()
    return event


def exclude_events_for_source(
    source_type: str,
    source_id: int,
    *,
    user_id: int | None,
    note: str = "原始紀錄已刪除。",
) -> int:
    events = AbnormalEvent.query.filter_by(
        source_type=source_type, source_id=source_id
    ).all()
    changed = 0
    for event in events:
        if event.status not in ("resolved", "dismissed"):
            event.status = "dismissed"
            event.resolved_by = user_id
            event.resolved_at = datetime.now()
            event.handling_note = (
                f"{event.handling_note}\n{note}".strip()
                if event.handling_note
                else note
            )
            changed += 1
    return changed
