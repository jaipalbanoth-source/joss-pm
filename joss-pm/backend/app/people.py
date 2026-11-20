"""Associate-name resolution used by the chat agents (Rahul -> Rahul Patil)."""
from __future__ import annotations
import re

STOP = {"the", "and", "for", "from", "task", "tasks", "role", "line", "lead", "manager", "project",
        "make", "add", "create", "end", "start", "date", "with", "this", "that", "new", "tech",
        "yes", "now", "all", "per", "not", "set", "assign", "release", "update", "move", "extend"}


def _words(s: str):
    return re.findall(r"[A-Za-z][A-Za-z'\.]*", s.replace("’", "'"))


def find_people(message: str, candidates: list[dict], pool_ids: set | None = None):
    """Return (resolved, ambiguous).
    resolved:  [associate dict]   (unique match per mention)
    ambiguous: [(token, [associates])] when one mention matches several people.
    When `pool_ids` is given, a mention that matches several people is narrowed to the pool first."""
    msg = message.replace("’", "'")
    low = msg.lower()
    resolved, ambiguous, used = [], [], set()
    # 1. full-name mentions
    for c in candidates:
        n = c["name"].lower()
        if re.search(r"\b" + re.escape(n) + r"\b", low):
            resolved.append(c)
            used.update(n.split())
    # 2. single-token mentions
    seen_tokens = set()
    for w in _words(msg):
        t = re.sub(r"'s?$", "", w.lower()).strip(".")
        if len(t) < 3 or t in STOP or t in used or t in seen_tokens:
            continue
        seen_tokens.add(t)
        hits = [c for c in candidates if t in [p.lower() for p in c["name"].split()]]
        if not hits:
            continue
        if len(hits) > 1 and pool_ids:
            narrowed = [h for h in hits if h["associate_id"] in pool_ids]
            if narrowed:
                hits = narrowed
        if len(hits) == 1:
            if hits[0] not in resolved:
                resolved.append(hits[0])
        else:
            if not any(h in resolved for h in hits):
                ambiguous.append((t, hits))
    return resolved, ambiguous
