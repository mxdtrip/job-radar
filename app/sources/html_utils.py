from __future__ import annotations

import re
from datetime import datetime, timezone

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def parse_ru_date(text: str) -> datetime | None:
    match = re.search(r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?\b", text.lower())
    if not match:
        return None
    now = datetime.now(timezone.utc)
    day, month_name, year = match.groups()
    year_num = int(year) if year else now.year
    candidate = datetime(year_num, RU_MONTHS[month_name], int(day), tzinfo=timezone.utc)
    if not year and candidate > now:
        candidate = candidate.replace(year=now.year - 1)
    return candidate


def parse_salary_ru(text: str) -> tuple[int | None, int | None, str | None]:
    compact = text.replace("\xa0", " ")
    nums = [int(n.replace(" ", "")) for n in re.findall(r"(?<!\d)(\d{2,3}(?:\s?\d{3})+)(?!\d)", compact)]
    currency = "RUR" if ("₽" in compact or "руб" in compact.lower()) else ("USD" if "$" in compact else None)
    if not nums:
        return None, None, currency
    lower = compact.lower()
    if "до " in lower and "от " not in lower:
        return None, nums[0], currency
    if "от " in lower and ("до " not in lower or len(nums) == 1):
        return nums[0], None, currency
    return nums[0], nums[1] if len(nums) > 1 else nums[0], currency


def clean_text(text: str, limit: int = 12000) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:limit]
