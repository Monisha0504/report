"""Period maths. A 'week' is any 7-day block (17 Nov -> 23 Nov); blocks repeat every 7 days from WEEK_ANCHOR.
Arbitrary ranges are supported too: the comparison periods are simply equal-length blocks before it."""
from __future__ import annotations

from datetime import date, timedelta

from . import config


def default_range(today: date | None = None) -> tuple[date, date]:
    """Latest anchored week that has fully finished (ends on or before yesterday)."""
    today = today or date.today()
    yesterday = today - timedelta(days=1)
    k = (yesterday - config.WEEK_ANCHOR).days // 7  # whole weeks since anchor
    # week k covers anchor+7k .. anchor+7k+6; need its end <= yesterday
    if config.WEEK_ANCHOR + timedelta(days=7 * k + 6) > yesterday:
        k -= 1
    start = config.WEEK_ANCHOR + timedelta(days=7 * k)
    return start, start + timedelta(days=6)


def shift(start: date, end: date, n: int) -> tuple[date, date]:
    """The block n periods earlier (n>0) or later (n<0) with the same length."""
    length = (end - start).days + 1
    d = timedelta(days=length * n)
    return start - d, end - d


def trend_periods(start: date, end: date, n: int = 3) -> list[tuple[date, date]]:
    """n consecutive equal-length periods ending with [start, end], oldest first."""
    return [shift(start, end, i) for i in range(n - 1, -1, -1)]


def label(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day}–{end.day} {end.strftime('%b')}"
    return f"{start.day} {start.strftime('%b')} – {end.day} {end.strftime('%b')}"
