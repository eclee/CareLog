"""Medication schedule snapshots and strictly forward-looking adherence."""

from datetime import timedelta

from models import MedPlanVersion, MedRecord, db


def snapshot_plan(plan, *, effective_on):
    version = MedPlanVersion(
        med_plan_id=plan.id, elder_id=plan.elder_id, effective_on=effective_on,
        name=plan.name, timeslot=plan.timeslot, meal_relation=plan.meal_relation,
        dose_note=plan.dose_note, active=plan.active,
    )
    db.session.add(version)
    db.session.flush()
    return version


def plan_adherence(elder_id, start, end):
    """Only dates with known schedule versions count toward the denominator."""
    versions = MedPlanVersion.query.filter(
        MedPlanVersion.elder_id == elder_id,
        MedPlanVersion.effective_on <= end,
    ).order_by(MedPlanVersion.effective_on, MedPlanVersion.id).all()
    if not versions:
        return {"rate": None, "scheduled": 0, "given": 0, "not_given": 0,
                "unreported": 0, "first_known_date": None}
    by_plan = {}
    for version in versions:
        by_plan.setdefault(version.med_plan_id, []).append(version)
    records = MedRecord.query.filter(
        MedRecord.elder_id == elder_id, MedRecord.record_date >= start,
        MedRecord.record_date <= end,
    ).all()
    reported = {(record.med_plan_id, record.record_date): record for record in records}
    scheduled = given = not_given = unreported = 0
    first_known_date = min(item.effective_on for item in versions)
    for plan_id, history in by_plan.items():
        for idx, version in enumerate(history):
            next_day = history[idx + 1].effective_on if idx + 1 < len(history) else end + timedelta(days=1)
            first = max(start, version.effective_on)
            last = min(end, next_day - timedelta(days=1))
            if not version.active or last < first:
                continue
            for offset in range((last - first).days + 1):
                day = first + timedelta(days=offset)
                scheduled += 1
                record = reported.get((plan_id, day))
                if record is None:
                    unreported += 1
                elif record.given:
                    given += 1
                else:
                    not_given += 1
    return {"rate": round(given * 100 / scheduled) if scheduled else None,
            "scheduled": scheduled, "given": given, "not_given": not_given,
            "unreported": unreported, "first_known_date": first_known_date.isoformat()}
