"""Reading and ordering Vietnamese reporting periods.

Sorting periods as text puts "Quý IV/2025" before "Quý I/2026" only by accident,
and puts "Tháng 10" before "Tháng 2". An animation ordered that way is simply
wrong, so periods are parsed into a real chronological key.

Handled: ``2020``, ``Năm 2020``, ``Quý I/2026``, ``Q2 2026``, ``Tháng 3/2026``,
``T3/2026``, ``03/2026``, ``2026-03``, ``2026-03-15``.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Sequence

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

YEAR = "year"
QUARTER = "quarter"
MONTH = "month"
DAY = "day"
UNKNOWN = "unknown"


def _deaccent(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", value)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def parse(value: Any) -> tuple[int, int, int, str] | None:
    """Return ``(year, month-ish, day, granularity)`` or None when unreadable.

    Quarters are stored as their first month so a quarter and a month series
    sort against each other sensibly.
    """
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return (value.year, value.month, getattr(value, "day", 1), DAY)

    text = _deaccent(str(value)).strip()
    if not text:
        return None

    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), DAY)

    m = re.search(r"qu[yy]?\s*([ivx]+|\d)\s*[/\- ]\s*(\d{4})", text)
    if m:
        token = m.group(1)
        quarter = ROMAN.get(token, int(token) if token.isdigit() else 0)
        if 1 <= quarter <= 4:
            return (int(m.group(2)), (quarter - 1) * 3 + 1, 1, QUARTER)

    m = re.search(r"\b(?:thang|t)\s*(\d{1,2})\s*[/\- ]\s*(\d{4})", text)
    if m and 1 <= int(m.group(1)) <= 12:
        return (int(m.group(2)), int(m.group(1)), 1, MONTH)

    m = re.search(r"(\d{4})[-/](\d{1,2})(?!\d)", text)
    if m and 1 <= int(m.group(2)) <= 12:
        return (int(m.group(1)), int(m.group(2)), 1, MONTH)

    m = re.search(r"(?<!\d)(\d{1,2})[/-](\d{4})(?!\d)", text)
    if m and 1 <= int(m.group(1)) <= 12:
        return (int(m.group(2)), int(m.group(1)), 1, MONTH)

    m = re.search(r"(?<!\d)(19|20)(\d{2})(?!\d)", text)
    if m:
        return (int(m.group(1) + m.group(2)), 1, 1, YEAR)
    return None


def sort_key(value: Any) -> tuple[int, int, int, str]:
    """Unparsable values sort last, keeping their own order stable."""
    parsed = parse(value)
    return parsed[:3] + (str(value),) if parsed else (9999, 99, 99, str(value))


def ordered(values: Sequence[Any]) -> list[Any]:
    """Distinct periods in chronological order, first appearance wins on ties."""
    seen: dict[str, Any] = {}
    for v in values:
        if v is None:
            continue
        key = str(v).strip()
        if key and key.lower() not in {"nan", "none", "nat"} and key not in seen:
            seen[key] = v
    return sorted(seen.values(), key=sort_key)


def granularity(values: Sequence[Any]) -> str:
    kinds = {parse(v)[3] for v in values if parse(v)}
    for kind in (DAY, MONTH, QUARTER, YEAR):
        if kind in kinds:
            return kind
    return UNKNOWN


def unreadable(values: Sequence[Any]) -> list[Any]:
    return [v for v in ordered(values) if parse(v) is None]


def label(value: Any) -> str:
    return str(value).strip()
