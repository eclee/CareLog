from datetime import date, datetime

from models import Elder, MealRecord, SentLog, db, get_care_parameters, get_setting
from services.abnormal import evaluate_daily_water
from services.mailer import MailNotConfigured, send_mail
from services.reports import build_report


SLOT_ZH = {"morning": "早上", "noon": "中午", "evening": "晚上", "bedtime": "睡前"}


def _already_sent(ref):
    return db.session.query(SentLog.id).filter_by(ref=ref).first() is not None


def _mark_sent(ref):
    db.session.add(SentLog(ref=ref))
    db.session.commit()


def _time_reached(now, hhmm):
    try:
        hour, minute = map(int, hhmm.split(":"))
    except (ValueError, AttributeError):
        return False
    return (now.hour, now.minute) >= (hour, minute)


def _try_send_report(period, ref):
    if _already_sent(ref):
        return
    try:
        subject, html, pdf = build_report(period)
        send_mail(subject, html, pdf)
        _mark_sent(ref)
    except MailNotConfigured:
        _mark_sent(ref)
    except Exception:
        # A transient failure can be retried on the next scheduler pass.
        db.session.rollback()


def run_scheduled_tasks(app):
    """Run report, reminder and daily abnormal checks once per minute."""

    with app.app_context():
        now = datetime.now()
        today = date.today()

        daily = get_setting("report_daily") or {}
        if daily.get("enabled") and _time_reached(now, daily.get("time", "21:00")):
            _try_send_report("daily", f"report_daily:{today}")

        weekly = get_setting("report_weekly") or {}
        if (
            weekly.get("enabled")
            and now.weekday() == int(weekly.get("weekday", 6))
            and _time_reached(now, weekly.get("time", "20:00"))
        ):
            _try_send_report("weekly", f"report_weekly:{today}")

        monthly = get_setting("report_monthly") or {}
        if (
            monthly.get("enabled")
            and now.day == int(monthly.get("day", 1))
            and _time_reached(now, monthly.get("time", "09:00"))
        ):
            _try_send_report(
                "monthly", f"report_monthly:{today.strftime('%Y-%m')}"
            )

        _check_reminders(now, today)
        _check_daily_water(now, today)


def _check_daily_water(now, today):
    rules = (get_care_parameters().get("abnormal_rules") or {})
    if not rules.get("water_low_enabled", False):
        return
    close_time = rules.get("water_close_time", "22:00")
    if not _time_reached(now, close_time):
        return
    for elder in Elder.query.filter_by(active=True).all():
        try:
            evaluate_daily_water(elder, today)
        except Exception:
            db.session.rollback()


def _check_reminders(now, today):
    reminders = get_setting("reminders") or {}
    if not reminders.get("enabled"):
        return
    elders = Elder.query.filter_by(active=True).all()
    for slot in ("morning", "noon", "evening", "bedtime"):
        deadline = reminders.get(slot)
        if not deadline or not _time_reached(now, deadline):
            continue
        for elder in elders:
            ref = f"reminder:{today}:{slot}:{elder.id}"
            if _already_sent(ref):
                continue
            has_record = (
                MealRecord.query.filter_by(
                    elder_id=elder.id, record_date=today, timeslot=slot
                ).first()
                is not None
            )
            if has_record:
                _mark_sent(ref)
                continue
            html = f"""
            <div style="font-family:'Noto Sans TC',sans-serif;max-width:560px;margin:auto;">
              <div style="background:#E8A13C;color:#fff;padding:14px 18px;
                          border-radius:10px 10px 0 0;font-size:17px;font-weight:700;">
                ⏰ 填報提醒</div>
              <div style="border:1px solid #f0e4d0;border-top:none;padding:18px;
                          border-radius:0 0 10px 10px;">
                <p>長輩 <b>{elder.name}</b> 的「{SLOT_ZH[slot]}」餐飲紀錄尚未填報
                （截止提醒時間 {deadline}）。</p>
                <p style="color:#6b7a76;font-size:13px;">請提醒照顧者盡快完成填報。</p>
              </div></div>"""
            try:
                send_mail(
                    f"⏰ 提醒：{elder.name} {SLOT_ZH[slot]}紀錄尚未填報", html
                )
                _mark_sent(ref)
            except MailNotConfigured:
                _mark_sent(ref)
            except Exception:
                db.session.rollback()
