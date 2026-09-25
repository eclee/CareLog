"""Shared reporting calculations. Missing observations are not recorded zeros."""

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func

from models import MealRecord, WaterRecord, db


def daily_fluids(elder_id, start, end):
    """Return {day: {water, supplement, unknown}} for days with entries."""
    days = defaultdict(lambda: {"water": 0, "supplement": 0, "unknown": 0})
    water = (
        db.session.query(WaterRecord.record_date, func.sum(WaterRecord.amount))
        .filter(WaterRecord.elder_id == elder_id,
                WaterRecord.record_date >= start, WaterRecord.record_date <= end)
        .group_by(WaterRecord.record_date)
        .all()
    )
    for day, amount in water:
        days[day]["water"] = int(amount or 0)
    supplements = (
        db.session.query(MealRecord.record_date, MealRecord.supplement_cc)
        .filter(MealRecord.elder_id == elder_id, MealRecord.record_date >= start,
                MealRecord.record_date <= end, MealRecord.supplement.is_(True))
        .all()
    )
    for day, amount in supplements:
        if amount is None:
            days[day]["unknown"] += 1
        else:
            days[day]["supplement"] += amount
    return dict(days)


def fluid_summary(days, start, end):
    values = [entry["water"] + entry["supplement"] for entry in days.values()
              if entry["water"] or entry["supplement"] or not entry["unknown"]]
    length = (end - start).days + 1
    return {
        "avg": round(sum(values) / len(values)) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "count": len(values),
        "period_avg": round(sum(values) / length) if values else None,
        "recorded_days": len(values),
        "total_days": length,
        "water_ml": sum(entry["water"] for entry in days.values()),
        "supplement_ml": sum(entry["supplement"] for entry in days.values()),
        "unknown_supplements": sum(entry["unknown"] for entry in days.values()),
    }


def period_buckets(start, end):
    """Return a stable, bounded number of daily, weekly or monthly chart bars."""
    length = (end - start).days + 1
    if length <= 90:
        key = lambda day: day
    elif length <= 730:
        key = lambda day: day - timedelta(days=day.weekday())
    else:
        key = lambda day: day.replace(day=1)
    buckets = []
    day = start
    while day <= end:
        label = key(day).isoformat()
        if not buckets or buckets[-1] != label:
            buckets.append(label)
        day += timedelta(days=1)
    return buckets, key
