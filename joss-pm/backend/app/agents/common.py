"""Small NLU helpers shared by the chat agents (A3/A4/A5)."""
from __future__ import annotations
import re
from ..dates import find_dates, parse_iso

START_RE = re.compile(r"(?:from|start\w*|begin\w*|commenc\w*|since)(?:\s+date)?\W*(?:on|at|as|of|is|to)?\W*$", re.I)
END_RE = re.compile(r"(?:to|until|till|through|thru|by|end\w*|finish\w*|due|before)(?:\s+date)?\W*(?:on|at|as|of|is|to)?\W*$", re.I)
YES = {"yes", "y", "yep", "yeah", "sure", "ok", "okay", "true", "yup", "billable"}
NO = {"no", "n", "nope", "false", "nah"}


def labelled_dates(text: str, ref: str | None):
    """[(iso, 'start'|'end'|None)] using the words just before each date."""
    out, prev_end = [], 0
    for d, a, b in find_dates(text, parse_iso(ref)):
        pre = text[max(prev_end, a - 30):a]
        label = "start" if START_RE.search(pre) else "end" if END_RE.search(pre) else None
        out.append((d, label))
        prev_end = b
    return out


def percent(text: str):
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|pct)", text, re.I) or \
        re.search(r"(?:utili[sz]ation|allocation|alloc)\D{0,12}(\d{1,3}(?:\.\d+)?)", text, re.I)
    return float(m.group(1)) if m else None


def yes_no(text: str):
    words = re.findall(r"[a-z]+", text.lower())
    if re.search(r"non[- ]?billable|not billable", text, re.I):
        return False
    for w in words:
        if w in YES:
            return True
        if w in NO:
            return False
    return None


def numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(items, 1))


def title(name: str) -> str:
    name = name.strip(" .,:;\"'")
    return name.title() if name.islower() else name


def split_names(part: str) -> list[str]:
    part = re.sub(r"(?i)^(?:tasks?|the following)[: ]*", "", part.strip())
    pieces = re.split(r",|\band\b|&|;", part)
    return [title(p) for p in pieces if p.strip(" .,:;") and not re.fullmatch(r"(?i)\s*(a|an|the|task|tasks)\s*", p)]


def reply(text, status, **kw):
    r = {"reply": text, "status": status, "changes": [], "missing": [], "rule_hits": [], "pending": None, "preview": None}
    r.update(kw)
    return r
