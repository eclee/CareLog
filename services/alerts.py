from html import escape

from flask import current_app

from models import get_setting
from services.mailer import send_mail, MailNotConfigured
from translations import tr, tr_format


def check_and_alert(elder, vital, lang="zh"):
    """Check a new vital record against thresholds; email immediately when abnormal.
    Returns localized warning strings for the caregiver interface."""
    th = get_setting("thresholds") or {}
    if not th.get("enabled", True):
        return []

    events = []

    def chk(value, hi_key, lo_key, label_key, label_zh, unit):
        if value is None:
            return
        hi, lo = th.get(hi_key), th.get(lo_key)
        if hi is not None and value >= hi:
            events.append(("high", label_key, label_zh, value, unit, hi))
        elif lo is not None and value <= lo:
            events.append(("low", label_key, label_zh, value, unit, lo))

    chk(vital.systolic, "sys_hi", "sys_lo", "systolic", "收縮壓", " mmHg")
    chk(vital.diastolic, "dia_hi", "dia_lo", "diastolic", "舒張壓", " mmHg")
    chk(vital.pulse, "pulse_hi", "pulse_lo", "pulse", "脈搏", " bpm")
    if vital.spo2 is not None and th.get("spo2_lo") is not None and vital.spo2 <= th["spo2_lo"]:
        events.append(("low", "spo2", "血氧", vital.spo2, "%", th["spo2_lo"]))

    if events:
        email_warnings = [
            f"{label_zh} {value}{unit} 偏{'高' if direction == 'high' else '低'}"
            f"（警戒值 {'≥' if direction == 'high' else '≤'} {threshold}）"
            for direction, _label_key, label_zh, value, unit, threshold in events
        ]
        items = "".join(
            f"<li style='margin:4px 0;'>{escape(warning)}</li>"
            for warning in email_warnings
        )
        safe_elder_name = escape(elder.name)
        html = f"""
        <div style="font-family:'Noto Sans TC',sans-serif;max-width:560px;margin:auto;">
          <div style="background:#C4534A;color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;
                      font-size:17px;font-weight:700;">⚠️ 健康數據異常警示</div>
          <div style="border:1px solid #eadcda;border-top:none;padding:18px;border-radius:0 0 10px 10px;">
            <p>長輩 <b>{safe_elder_name}</b> 於 {vital.recorded_at:%Y-%m-%d %H:%M} 的量測數據超出警戒範圍：</p>
            <ul>{items}</ul>
            <p style="color:#6b7a76;font-size:13px;">請儘速確認長輩狀況，必要時聯繫醫療人員。</p>
          </div></div>"""
        try:
            send_mail(f"⚠️ 異常警示：{elder.name} 健康數據超標", html)
        except MailNotConfigured:
            pass  # Email is optional and must never block saving the care record.
        except Exception:
            current_app.logger.exception("Abnormal-vital alert email failed")

    return [
        tr_format(
            lang,
            f"alert_{direction}",
            label=tr(lang, label_key),
            value=value,
            unit=unit,
            threshold=threshold,
        )
        for direction, label_key, _label_zh, value, unit, threshold in events
    ]
