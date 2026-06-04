from datetime import date, timedelta
from typing import Dict, Optional


def _first_of_next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _window(period: str, start: date, end: date, label: str) -> Dict[str, str]:
    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "label": f"{label} ({start.isoformat()} to {(end - timedelta(days=1)).isoformat()})",
    }


def resolve_sales_window(
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    today: Optional[date] = None,
) -> Dict[str, str]:
    current = today or date.today()
    period = (period or "past_year").strip().lower()

    if start_date and end_date:
        start = date.fromisoformat(start_date)
        end_inclusive = date.fromisoformat(end_date)
        if end_inclusive < start:
            start, end_inclusive = end_inclusive, start
        return _window("custom", start, end_inclusive + timedelta(days=1), "Custom range")

    if period == "this_month":
        return _window(period, current.replace(day=1), current + timedelta(days=1), "This month to date")
    if period == "last_month":
        end = current.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
        return _window(period, start, end, "Last month")
    if period == "this_year":
        return _window(period, date(current.year, 1, 1), current + timedelta(days=1), "This year to date")
    if period == "last_year":
        return _window(period, date(current.year - 1, 1, 1), date(current.year, 1, 1), "Last year")
    if period == "past_month":
        return _window(period, current - timedelta(days=30), current + timedelta(days=1), "Past 30 days")
    if period == "past_year":
        return _window(period, current - timedelta(days=365), current + timedelta(days=1), "Past 12 months")
    raise ValueError(f"Unsupported sales report period: {period}")
