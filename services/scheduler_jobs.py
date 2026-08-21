from datetime import datetime, date

from models import db, get_setting, SentLog, Elder, MealRecord
from services.mailer import send_mail, MailNotConfigured
from services.reports import build_report

SLOT_ZH = {"morning": "早上", "noon": "中午", "evening": "晚上", "bedtime": "睡前"}


def _already_sent(ref):
    return db.session.query(SentLog.id).filter_by(ref=ref).first() is not None


def _mark_sent(ref):
    db.session.add(SentLog(ref=ref))
    db.session.commit()


def _time_reached(now, hhmm):
    try:
        h, m = map(int, hhmm.split(":"))
    except (ValueError, AttributeError):
        return False
    return (now.hour, now.minute) >= (h, m)


def _try_send_report(period, ref):
    if _already_sent(ref):
        return
    try:
        subject, html, pdf = build_report(period)
        send_mail(subject, html, pdf)
        _mark_sent(ref)
    except MailNotConfigured:
        _mark_sent(ref)  # skip quietly until mail is configured
    except Exception:
        pass  # transient failure: retry next minute


def run_scheduled_tasks(app):
    """Runs every minute inside app context."""
    with app.app_context():
        now = datetime.now()
        today = date.today()

        d = get_setting("report_daily") or {}
        if d.get("enabled") and _time_reached(now, d.get("time", "21:00")):
            _try_send_report("daily", f"report_daily:{today}")

        w = get_setting("report_weekly") or {}
        if (w.get("enabled") and now.weekday() == int(w.get("weekday", 6))
                and _time_reached(now, w.get("time", "20:00"))):
            _try_send_report("weekly", f"report_weekly:{today}")

        m = get_setting("report_monthly") or {}
        if (m.get("enabled") and now.day == int(m.get("day", 1))
                and _time_reached(now, m.get("time", "09:00"))):
            _try_send_report("monthly", f"report_monthly:{today.strftime('%Y-%m')}")

        _check_reminders(now, today)


def _check_reminders(now, today):
    r = get_setting("reminders") or {}
    if not r.get("enabled"):
        return
    elders = Elder.query.filter_by(active=True).all()
    for slot in ("morning", "noon", "evening", "bedtime"):
        deadline = r.get(slot)
        if not deadline or not _time_reached(now, deadline):
            continue
        for e in elders:
            ref = f"reminder:{today}:{slot}:{e.id}"
            if _already_sent(ref):
                continue
            has = (MealRecord.query
                   .filter_by(elder_id=e.id, record_date=today, timeslot=slot)
                   .first() is not None)
            if has:
                _mark_sent(ref)
                continue
            html = f"""
            <div style="font-family:'Noto Sans TC',sans-serif;max-width:560px;margin:auto;">
              <div style="background:#E8A13C;color:#fff;padding:14px 18px;
                          border-radius:10px 10px 0 0;font-size:17px;font-weight:700;">
                ⏰ 填報提醒</div>
              <div style="border:1px solid #f0e4d0;border-top:none;padding:18px;
                          border-radius:0 0 10px 10px;">
                <p>長輩 <b>{e.name}</b> 的「{SLOT_ZH[slot]}」餐飲紀錄尚未填報
                （截止提醒時間 {deadline}）。</p>
                <p style="color:#6b7a76;font-size:13px;">請提醒照顧者盡快完成填報。</p>
              </div></div>"""
            try:
                send_mail(f"⏰ 提醒：{e.name} {SLOT_ZH[slot]}紀錄尚未填報", html)
                _mark_sent(ref)
            except MailNotConfigured:
                _mark_sent(ref)
            except Exception:
                pass
