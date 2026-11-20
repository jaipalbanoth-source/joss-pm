"""A4 - Jade Contacts Agent. Chat, change-only JSON. Assigns roles to associates and handles automatic handover:
when a single-holder role changes hands the previous holder's end date becomes (new start - 1 day)  [JC-03].
Both changes (close old + create new) are staged together or not at all."""
from __future__ import annotations
import re

from .. import context as C
from .. import ops, rules
from ..dates import day_before, fmt
from ..people import find_people
from .common import labelled_dates, numbered, reply

ROLE_PATTERNS = [("Project Manager", r"project manager|\bpm\b"), ("Tech Lead", r"tech(?:nical)?\s+lead|\btl\b"),
                 ("Delivery Manager", r"delivery manager|\bdm\b"), ("Functional Consultant", r"functional consultant|\bfc\b"),
                 ("Technical Consultant", r"technical consultant"), ("QA Lead", r"qa lead|test lead")]
END_RE = re.compile(r"\b(end|close|release|stop|terminate|roll off|remove|finish)\b", re.I)
ASK = {"role": "Which role (e.g. Project Manager, Tech Lead, Delivery Manager, Functional Consultant)?",
       "associate": "Which associate (name, email or employee ID)?", "start": "From which date does the role start?"}


def parse_role(text, roles):
    for role, pat in ROLE_PATTERNS:
        if role in roles and re.search(pat, text, re.I):
            return role
    return None


def _people(text, refs):
    d = list(refs["directory"].values())
    for a in d:
        for key in (a["email"], a["associate_id"]):
            if key and key.lower() in text.lower():
                return [a], []
    return find_people(text, d)


def _card(ctx, refs, role, aid, start, end):
    return f"{role} → {refs['directory'][aid]['name']} from {fmt(start)} to {fmt(end) if end else 'project finish'}"


def run(ctx: dict, refs: dict, message: str, pending: dict | None = None, structured: dict | None = None) -> dict:
    text = (message or "").strip()
    s, f = C.project_dates(ctx)
    roles = refs["roles"]
    if structured:
        st = structured
        return _plan(ctx, refs, {"role": st.get("role"), "associate_id": st.get("associate_id"), "start": st.get("start"), "end": st.get("end")})
    if re.fullmatch(r"\W*(cancel|never ?mind|discard|forget it)\W*", text, re.I):
        return reply("Okay, discarded. Nothing was staged.", "info")

    draft = dict(pending["draft"]) if pending and pending.get("draft") else {}
    # numbered answer to an ambiguity question
    m = re.fullmatch(r"\W*(\d)\W*", text)
    if m and pending and pending.get("candidates"):
        i = int(m.group(1)) - 1
        if 0 <= i < len(pending["candidates"]):
            draft["associate_id"] = pending["candidates"][i]
            return _plan(ctx, refs, draft)
    people, ambiguous = _people(text, refs)
    role = parse_role(text, roles)
    dates = labelled_dates(text, draft.get("start") or s)

    # ---- end a role / release
    if END_RE.search(text) and not re.search(r"\b(make|assign|appoint|set)\b", text, re.I) and (people or role):
        return _end_role(ctx, refs, text, people, role, dates)

    if role:
        draft["role"] = role
    if people:
        draft["associate_id"] = people[0]["associate_id"]
    st = next((d for d, l in dates if l == "start"), None)
    en = next((d for d, l in dates if l == "end"), None)
    free = [d for d, l in dates if l is None]
    if not st and free:
        st = free.pop(0)
    if not en and free:
        en = free.pop(0)
    if st:
        draft["start"] = st
    if en:
        draft["end"] = en
    if re.search(r"project (end|finish)|till the end|until the end", text, re.I):
        draft["end"] = None
    if not people and ambiguous and not draft.get("associate_id"):
        tok, hits = ambiguous[0]
        return reply(f"'{tok.title()}' matches more than one person - which one?\n" + numbered([f"{h['name']} ({h['title']}, {h['location']}) - {h['email']}" for h in hits]),
                     "needs_info", pending={"draft": draft, "candidates": [h["associate_id"] for h in hits], "missing": ["associate"]}, missing=["associate"])
    return _plan(ctx, refs, draft)


def _plan(ctx, refs, draft):
    miss = [k for k, v in (("role", draft.get("role")), ("associate", draft.get("associate_id")), ("start", draft.get("start"))) if not v]
    if miss:
        return reply("Got it. I need " + ("one more detail" if len(miss) == 1 else f"{len(miss)} more details") + ":\n" + numbered([ASK[m] for m in miss]),
                     "needs_info", pending={"draft": draft, "missing": miss}, missing=miss)
    role, aid, start, end = draft["role"], draft["associate_id"], draft["start"], draft.get("end")
    a = refs["directory"].get(aid)
    if not a:
        return reply(f"No associate {aid} in the directory (JC-04).", "blocked")
    if a["status"] != "active":
        return reply(f"JC-04: {a['name']} is not an active employee, so cannot hold a role. Pick someone else.", "blocked",
                     rule_hits=[rules.hit("JC-04", "BLOCK", f"{a['name']} is not an active employee.")], pending={"draft": {**draft, "associate_id": None}, "missing": ["associate"]})
    s, f = C.project_dates(ctx)
    single = refs["roles"].get(role, False)
    changes, rows = [], []
    if single:
        prev = [c for c in ctx["contacts"] if c["role"] == role and c["start"] <= start and (c.get("end") or f or "9999-12-31") >= start]
        for p in prev:
            if p["associate_id"] == aid:
                return reply(f"{a['name']} already holds {role} on {fmt(start)}.", "blocked")
            if p["start"] >= start:
                return reply(f"JC-01: {role} is held by {refs['directory'][p['associate_id']]['name']} from {fmt(p['start'])}; "
                             f"a handover can't end before it starts. Choose a start after {fmt(p['start'])}.", "blocked",
                             rule_hits=[rules.hit("JC-01", "BLOCK", "Handover would end the previous holder before they start.")])
            new_end = day_before(start)
            changes.append({"op": "update", "contact_id": p["id"], "after": {"end": new_end}, "source": "handover"})
            rows.append({"action": "CLOSE", "role": role, "associate": refs["directory"][p["associate_id"]]["name"], "start": p["start"],
                         "end": new_end, "was": f"was: {'open-ended' if not p.get('end') else fmt(p['end'])}"})
    changes.append({"op": "add", "contact": {"role": role, "associate_id": aid, "start": start, "end": end, "source": "chat"}})
    rows.append({"action": "CREATE", "role": role, "associate": a["name"], "start": start, "end": end, "was": None if end else "Project finish (default)"})
    try:
        new, hits, blocks = ops.simulate(ctx, "contacts", changes, refs)
    except ops.OpError as e:
        return reply(e.message, "blocked", rule_hits=e.hits)
    if blocks:
        return reply("I can't stage that:\n" + "\n".join(f"• {h['id']}: {h['message']}" for h in blocks), "blocked", rule_hits=blocks,
                     pending={"draft": draft, "missing": []}, preview={"kind": "contacts", "rows": rows})
    extra = ""
    if role == "Project Manager":
        extra = f" {a['name']} will also become the timesheet approver in Edit Project (X-03)."
    hand = " Handover: previous holder's end date is set to the day before the new start (JC-03)." if len(changes) > 1 else ""
    warns = [h for h in hits if h["level"] == "WARN" and h["module"] == "contacts"]
    return reply(f"Ready.{hand}{extra}\nReview the preview and click Create.", "ready", changes=changes, rule_hits=warns,
                 preview={"kind": "contacts", "rows": rows, "approver_change": a["name"] if role == "Project Manager" else None})


def _end_role(ctx, refs, text, people, role, dates):
    s, f = C.project_dates(ctx)
    cands = [c for c in ctx["contacts"] if (not people or c["associate_id"] == people[0]["associate_id"]) and (not role or c["role"] == role)]
    if not cands:
        return reply("I couldn't find a matching contact to end. Tell me who and which role.", "needs_info", missing=["associate"])
    when = next((d for d, l in dates), None)
    if not when:
        return reply("On which date should the role end?\n1. End date?", "needs_info", missing=["end"],
                     pending={"draft": {"role": role, "associate_id": people[0]["associate_id"] if people else None}, "missing": ["end"]})
    cands.sort(key=lambda c: c["start"], reverse=True)
    c = cands[0]
    changes = [{"op": "update", "contact_id": c["id"], "after": {"end": when}, "source": "chat"}]
    try:
        new, hits, blocks = ops.simulate(ctx, "contacts", changes, refs)
    except ops.OpError as e:
        return reply(e.message, "blocked")
    rows = [{"action": "CLOSE", "role": c["role"], "associate": refs["directory"][c["associate_id"]]["name"], "start": c["start"], "end": when,
             "was": f"was: {fmt(c['end']) if c.get('end') else 'open-ended'}"}]
    if blocks:
        return reply("I can't stage that:\n" + "\n".join(f"• {h['id']}: {h['message']}" for h in blocks), "blocked", rule_hits=blocks, preview={"kind": "contacts", "rows": rows})
    warn = " Note: the project will have no Project Manager after this date (JC-05)." if c["role"] == "Project Manager" else ""
    return reply(f"Ready. End {c['role']} {rows[0]['associate']} on {fmt(when)}.{warn}\nClick Create to confirm.", "ready", changes=changes, preview={"kind": "contacts", "rows": rows})
