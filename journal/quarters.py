"""Учебные четверти 2026/2027 (Казахстан). Даты по приказу Минпросвещения РК.

Каникулы: осенние 26.10–01.11.2026, зимние 28.12.2026–10.01.2027, весенние 22–28.03.2027.
На новый учебный год достаточно заменить даты в QUARTERS.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

SCHOOL_YEAR = "2026/2027"
QUARTERS = {
    1: (date(2026, 9, 1), date(2026, 10, 25)),
    2: (date(2026, 11, 2), date(2026, 12, 27)),
    3: (date(2027, 1, 11), date(2027, 3, 21)),
    4: (date(2027, 3, 29), date(2027, 5, 25)),
}


def quarter_for(d: date) -> int | None:
    """Номер четверти для даты или None (каникулы / вне учебного года)."""
    for number, (start, end) in QUARTERS.items():
        if start <= d <= end:
            return number
    return None


def round_half_up(total: int, count: int) -> int:
    """Среднее с округлением по правилам математики: 6,5 → 7 (а не «банковское» 6,5 → 6)."""
    return int((Decimal(total) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def schedule_text() -> str:
    return " · ".join(
        f"{n} четверть: {s.strftime('%d.%m')}–{e.strftime('%d.%m.%Y')}" for n, (s, e) in QUARTERS.items()
    )
