"""Date parsing and experience computation. Years of experience are computed by code, never by the LLM."""
import re
from datetime import date
from typing import Iterable, List, Optional, Tuple

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
PRESENT_WORDS = {"present", "current", "now", "ongoing", "today", "till date", "to date", "till now"}

Period = Tuple[date, date]


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def parse_date(value: str, today: Optional[date] = None, is_end: bool = False) -> Optional[date]:
    """Parse 'Jan 2020', '01/2020', '2020-01', '2020' or 'present' to the first day of a month.

    A bare year maps to January for starts and December for ends. Dates in the future are clamped to today.
    """
    if value is None:
        return None
    today = today or date.today()
    s = value.strip().lower().rstrip(".")
    if not s:
        return None
    if s in PRESENT_WORDS:
        return date(today.year, today.month, 1)

    year = month = None
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    if year is None:
        m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", s)
        if m:
            month, year = int(m.group(1)), int(m.group(2))
    if year is None:
        m = re.fullmatch(r"([a-z]{3,9})\.?,?\s+(\d{4})", s)
        if m and m.group(1) in MONTHS:
            month, year = MONTHS[m.group(1)], int(m.group(2))
    if year is None:
        m = re.fullmatch(r"(\d{4})", s)
        if m:
            year = int(m.group(1))
            month = 12 if is_end else 1
    if year is None or month is None or not (1 <= month <= 12) or not (1950 <= year <= 2100):
        return None

    d = date(year, month, 1)
    return min(d, date(today.year, today.month, 1))


def merge_periods(periods: Iterable[Period]) -> List[Period]:
    """Merge overlapping or back-to-back (month-adjacent) periods so concurrent jobs are not double counted."""
    items = sorted((p for p in periods if p[0] <= p[1]), key=lambda p: p[0])
    merged: List[Period] = []
    for start, end in items:
        if merged and _month_index(start) <= _month_index(merged[-1][1]) + 1:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def total_years(periods: Iterable[Period]) -> float:
    """Total years across merged periods; both the start and end month count (Jan-Dec 2020 = 1.0)."""
    months = sum(_month_index(e) - _month_index(s) + 1 for s, e in merge_periods(periods))
    return round(months / 12.0, 1)


def years_of_experience(roles, today: Optional[date] = None) -> float:
    """Years of experience from role objects having .start and .end strings. Roles with no start are skipped;
    a missing end is read as present."""
    periods = []
    for r in roles:
        if not r.start:
            continue
        start = parse_date(r.start, today)
        end = parse_date(r.end, today, is_end=True) if r.end else parse_date("present", today)
        if start and end:
            periods.append((start, end))
    return total_years(periods)
