from __future__ import annotations

from datetime import date, datetime
import re
from typing import Optional


def parse_flexible_date(value: str | datetime | date | None) -> Optional[datetime]:
    """
    Parse flexible date inputs and return datetime.
    Accepted:
    - YYYY/MM/DD, YYYY-MM-DD, YYYY.MM.DD
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - YYYYMMDD, DDMMYYYY
    - ISO datetime/date strings
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in (
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
        "%y/%m/%d",
        "%Y%m%d",
        "%d%m%Y",
        "%d%m%y",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    digits = re.sub(r"\D", "", raw)
    if len(digits) == 8:
        yyyy, mm, dd = digits[:4], digits[4:6], digits[6:8]
        try:
            return datetime(int(yyyy), int(mm), int(dd))
        except ValueError:
            pass
        dd, mm, yyyy = digits[:2], digits[2:4], digits[4:8]
        try:
            return datetime(int(yyyy), int(mm), int(dd))
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_date_ymd(value: str | datetime | date | None) -> Optional[str]:
    dt = parse_flexible_date(value)
    if not dt:
        return None
    return dt.strftime("%Y/%m/%d")
