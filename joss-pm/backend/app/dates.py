"""Date + text helpers shared by the rule engine and the agents."""
from __future__ import annotations
import calendar
import re
from datetime import date, timedelta

MONTHS = {}
for i in range(1, 13):
    MONTHS[calendar.month_name[i].lower()] = i
    MONTHS[calendar.month_abbr[i].lower()] = i
MONTHS["sept"] = 9

_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_RE = re.compile(
    r"""(?P<iso>\d{4}-\d{2}-\d{2})
      |(?P<dmy>\b(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<m1>""" + _MON + r""")\b\.?(?:,?\s+(?P<y1>\d{4}))?)
      |(?P<mdy>\b(?P<m2>""" + _MON + r""")\b\.?\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(?P<y2>\d{4}))?)""",
    re.X | re.I,
)


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def parse_iso(s) -> date | None:
    if not s:
        return None
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def day_before(s: str) -> str:
    return (date.fromisoformat(s) - timedelta(days=1)).isoformat()


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _resolve_year(month: int, day: int, ref: date | None) -> date | None:
    ref = ref or date.today()
    for y in (ref.year, ref.year + 1):
        try:
            cand = date(y, month, day)
        except ValueError:
            return None
        if cand >= ref:
            return cand
    return None


def find_dates(text: str, ref: date | None = None):
    """Return [(iso, start, end)] for every date in text.
    Dates without a year are placed on/after `ref` (and after the previous date in the text)."""
    out = []
    running = ref
    for m in _DATE_RE.finditer(text or ""):
        try:
            if m.group("iso"):
                d = date.fromisoformat(m.group("iso"))
            elif m.group("dmy"):
                mon = MONTHS.get(m.group("m1").lower())
                if not mon:
                    continue
                day = int(m.group("d1"))
                if m.group("y1"):
                    d = date(int(m.group("y1")), mon, day)
                else:
                    d = _resolve_year(mon, day, running)
            else:
                mon = MONTHS.get(m.group("m2").lower())
                if not mon:
                    continue
                day = int(m.group("d2"))
                if m.group("y2"):
                    d = date(int(m.group("y2")), mon, day)
                else:
                    d = _resolve_year(mon, day, running)
        except (ValueError, TypeError):
            continue
        if d is None:
            continue
        out.append((d.isoformat(), m.start(), m.end()))
        running = d if (running is None or d > running) else running
    return out


def fmt(s: str | None) -> str:
    d = parse_iso(s)
    return d.strftime("%d %b %Y") if d else "—"


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    a_start, b_start = a_start or "0000-01-01", b_start or "0000-01-01"
    a_end, b_end = a_end or "9999-12-31", b_end or "9999-12-31"
    return a_start <= b_end and b_start <= a_end
