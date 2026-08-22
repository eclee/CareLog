from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from flask import request


@dataclass(frozen=True)
class DateRange:
    start_date: date | None
    end_date: date | None
    start_datetime: datetime | None
    end_datetime: datetime | None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def request_date_range(
    *,
    single_key: str = "date",
    start_key: str = "from",
    end_key: str = "to",
) -> DateRange:
    single = parse_date(request.args.get(single_key))
    if single:
        start_date = end_date = single
    else:
        start_date = parse_date(request.args.get(start_key))
        end_date = parse_date(request.args.get(end_key))
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

    start_datetime = (
        datetime.combine(start_date, time.min) if start_date is not None else None
    )
    end_datetime = (
        datetime.combine(end_date + timedelta(days=1), time.min)
        if end_date is not None
        else None
    )
    return DateRange(start_date, end_date, start_datetime, end_datetime)


def pagination_args(*, default_per_page: int = 50, max_per_page: int = 100):
    page = max(1, request.args.get("page", type=int) or 1)
    per_page = request.args.get("per_page", type=int) or default_per_page
    allowed = (25, 50, 100)
    if per_page not in allowed:
        per_page = default_per_page
    per_page = min(per_page, max_per_page)
    return page, per_page


def query_args_without(*keys: str) -> dict[str, str]:
    result = request.args.to_dict(flat=True)
    for key in keys:
        result.pop(key, None)
    return result
