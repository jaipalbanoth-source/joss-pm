"""A5 - Resource Management Agent. Chat, change-only JSON: assign / add / update / release / split resource lines.
An associate name is required (RM-02): a resource line is never created without one."""
from __future__ import annotations
import re

from .. import context as C
from .. import ops, rules
from ..dates import add_months, fmt, parse_iso
from ..people import find_people
from .common import labelled_dates, numbered, percent, reply

ROLE_WORDS = [("Project Manager", r"project manager|\bpm\b"), ("Technical Lead", r"tech(?:nical)? lead"), ("Functional Consultant", r"functional(?: consultant)?|\bfc\b"),
              ("Technical Consultant", r"technical consultant"), ("Developer", r"developer|\bdev\b|engineer(?! qa)"), ("QA Engineer", r"\bqa\b|tester|test engineer|quality"),
              ("Solution Architect", r"architect")]
FIELD_WORDS = {"bill_rate": r"bill(?:ing)?\s*rate|rate", "cost_rate": r"cost\s*rate", "hours": r"hours?", "level": r"level", "tier": r"tier",
               "location": r"location", "allocation_pct": r"allocation|alloc"}


def ln(ctx, line_id):
    for i, l in enumerate(ctx["resources"], 1):
        if l["id"] == line_id:
            return f"#{i}"
    return line_id


def _line_ref(ctx, text):
    m = re.search(r"\b(?:line|row|#)\s*(\d+)\b", text, re.I)
    if m:
        i = int(m.group(1)) - 1
        if 0 <= i < len(ctx["resources"]):
            return ctx["resources"][i]
    m = re.search(r"\b[rl](\d+)\b", text, re.I)
    if m:
        for l in ctx["resources"]:
            if l["id"] == f"r{m.group(1)}":
                return l
    return None


def _role(text):
    for role, pat in ROLE_WORDS:
        if re.search(pat, text, re.I):
            return role
    return None


def _impact(ctx, new, refs):
    a, b = C.totals(ctx), C.totals(new)
    tgt = C.val(new, "margin_target")
    msg = f"Budget {a['budget']:,.0f} → {b['budget']:,.0f}"
    if b["margin_pct"] is not None:
        msg += f"; margin {b['margin_pct']}%" + (f" (target {tgt:g}%)" if tgt is not None else "")
    return msg


def run(ctx: dict, refs: dict, message: str, pending: dict | None = None, structured: dict | None = None) -> dict:
    text = (message or "").strip()
    d = list(refs["directory"].values())
    pool_ids = {l["associate_id"] for l in ctx["resources"] if l.get("associate_id")}
    s, f = C.project_dates(ctx)

    if structured:
        return _from_structured(ctx, refs, structured)
    if re.fullmatch(r"\W*(cancel|never ?mind|discard|forget it)\W*", text, re.I):
        return reply("Okay, discarded. Nothing was staged.", "info")

    people, ambiguous = find_people(text, d, pool_ids)
    # --- answer to a pending add that lacked a name
    if pending and pending.get("intent") == "add":
        draft = dict(pending["draft"])
        if people:
            draft["associate_id"] = people[0]["associate_id"]
            return _add(ctx, refs, draft)
        if ambiguous:
            return _ambiguous(ambiguous[0], {"intent": "add", "draft": draft})
        return reply("I still need an associate name before I can create the resource (RM-02).\n1. Which associate?", "needs_info", pending=pending, missing=["associate"])
    if pending and pending.get("intent") == "assign" and (people or ambiguous):
        if people:
            return _assign(ctx, refs, pending["line_id"], people[0], text)
        return _ambiguous(ambiguous[0], pending)

    # --- split: "move 1 of the 4 TE3s to onshore"
    m = re.search(r"move\s+(\d+)\s+of\s+(?:the\s+)?(\d+)\s+(TE\d)s?\s*(?:[a-z ]*?)\s+to\s+(onshore|offshore)", text, re.I)
    if m:
        return _split(ctx, refs, int(m.group(1)), int(m.group(2)), m.group(3).upper(), m.group(4).lower())

    low = text.lower()
    if re.search(r"\b(release|roll off|rolloff|end)\b", low) and not re.search(r"\badd\b", low):
        return _release(ctx, refs, text, people)
    if re.search(r"\bunassign|remove .* from line|clear associate", low):
        line = _line_ref(ctx, text)
        if line:
            return _ready(ctx, refs, [{"op": "unassign", "line_id": line["id"]}], f"Remove the associate from line {ln(ctx, line['id'])}?")
    if re.match(r"^\W*(add|create|new)\b", low) and not re.search(r"\bline \d", low):
        return _add_from_text(ctx, refs, text, people, ambiguous)
    if re.search(r"\b(update|change|set|edit|increase|reduce|decrease)\b", low) and not re.search(r"\bassign\b", low):
        return _update(ctx, refs, text)
    if re.search(r"\b(assign|allocate|put|staff|give|use)\b", low) or people:
        return _assign_from_text(ctx, refs, text, people, ambiguous)
    return reply("I can assign, add, update, release or split resource lines. Try: \"assign Rahul to line 2\", "
                 "\"add 1 TE4 offshore QA - Priya\", \"release line 3 on 31 Dec\" or \"move 1 of the 4 TE3s to onshore\".", "info")


def _ambiguous(amb, pending):
    tok, hits = amb
    p = dict(pending)
    return reply(f"'{tok.title()}' matches more than one person - which one (use the full name)?\n" +
                 numbered([f"{h['name']} ({h['title']}, {h['location']})" for h in hits]), "needs_info", pending=p, missing=["associate"])


def _ready(ctx, refs, changes, lead, extra_preview=None):
    try:
        new, hits, blocks = ops.simulate(ctx, "resources", changes, refs)
    except ops.OpError as e:
        return reply(e.message, "blocked", rule_hits=e.hits)
    if blocks:
        return reply("I can't stage that:\n" + "\n".join(f"• {h['id']}: {h['message']}" for h in blocks), "blocked", rule_hits=blocks)
    warns = [h for h in hits if h["level"] == "WARN" and h["module"] in ("resources", "edit_project")]
    msg = f"{lead}\n{_impact(ctx, new, refs)}."
    if warns:
        msg += "\nWarnings:\n" + "\n".join(f"• {h['id']}: {h['message']}" for h in warns)
    msg += "\nReview the preview and click Apply."
    rows = []
    before = {l["id"]: l for l in ctx["resources"]}
    for l in new["resources"]:
        b = before.get(l["id"])
        if b is None or any(b.get(k) != l.get(k) for k in ("associate_id", "qty", "bill_rate", "cost_rate", "hours", "level", "location", "start", "end", "allocation_pct", "role", "released")):
            rows.append({"line_id": l["id"], "new": b is None, "before": b and {k: b.get(k) for k in ("associate_id", "qty", "location", "bill_rate", "hours", "level", "end", "allocation_pct")},
                         "after": {k: l.get(k) for k in ("associate_id", "qty", "location", "bill_rate", "hours", "level", "end", "allocation_pct", "role")}})
    return reply(msg, "ready", changes=changes, rule_hits=warns, preview={"kind": "resources", "rows": rows, "impact": _impact(ctx, new, refs)})


def _assign(ctx, refs, line_id, person, text=""):
    line = next((l for l in ctx["resources"] if l["id"] == line_id), None)
    if not line:
        return reply(f"Line {line_id} not found.", "blocked")
    ch = {"op": "assign", "line_id": line_id, "associate_id": person["associate_id"]}
    pct = percent(text)
    if pct:
        ch["allocation_pct"] = pct
    split = " (the line had quantity %g, so one unit is split off)" % line["qty"] if line["qty"] > 1 else ""
    return _ready(ctx, refs, [ch], f"Assign {person['name']} to line {ln(ctx, line_id)} ({line['role']} {line['level']} {line['location']}){split}.")


def _assign_from_text(ctx, refs, text, people, ambiguous):
    if not people:
        if ambiguous:
            line = _line_ref(ctx, text)
            return _ambiguous(ambiguous[0], {"intent": "assign", "line_id": line["id"] if line else None}) if line else \
                reply(f"'{ambiguous[0][0].title()}' matches several people; use the full name and a line number.", "needs_info")
        return reply("Which associate should I assign?", "needs_info", missing=["associate"])
    line = _line_ref(ctx, text)
    if not line:
        role = _role(text)
        lvl = re.search(r"\bTE\d\b", text, re.I)
        loc = re.search(r"\b(on|off)shore\b", text, re.I)
        cands = [l for l in ctx["resources"] if not l.get("associate_id") and not l.get("released") and (not role or l["role"] == role)
                 and (not lvl or l["level"] == lvl.group(0).upper()) and (not loc or l["location"] == loc.group(0).lower())]
        if len(cands) == 1 or (cands and role):
            line = cands[0]
        elif not cands:
            return reply("I couldn't find an unassigned line for that. Name the line number (e.g. 'assign Rahul to line 2').", "needs_info", missing=["line"])
        else:
            return reply("Which line?\n" + numbered([f"line {ctx['resources'].index(l) + 1}: {l['role']} {l['level']} {l['location']}" for l in cands[:8]]), "needs_info",
                         pending={"intent": "assign", "line_id": None}, missing=["line"])
    return _assign(ctx, refs, line["id"], people[0], text)


def _add_from_text(ctx, refs, text, people, ambiguous):
    lvl = re.search(r"\bTE\s?(\d)\b", text, re.I)
    loc = re.search(r"\b(on|off)shore\b", text, re.I)
    role = _role(re.sub(r"\bTE\s?\d\b", "", text, flags=re.I))
    qty = re.search(r"\badd\s+(\d+)\b", text, re.I)
    draft = {"role": role, "level": f"TE{lvl.group(1)}" if lvl else None, "location": loc.group(0).lower() if loc else None,
             "qty": int(qty.group(1)) if qty else 1}
    for k, v in (("bill_rate", r"bill\s*rate\D{0,6}(\d+(?:\.\d+)?)"), ("hours", r"(\d+)\s*h(?:ou)?rs?")):
        m = re.search(v, text, re.I)
        if m:
            draft[k] = float(m.group(1))
    if people:
        draft["associate_id"] = people[0]["associate_id"]
    elif ambiguous:
        return _ambiguous(ambiguous[0], {"intent": "add", "draft": draft})
    return _add(ctx, refs, draft)


def _add(ctx, refs, draft):
    missing = [k for k in ("role", "level", "location") if not draft.get(k)]
    if missing:
        return reply("To add a resource I need:\n" + numbered([{"role": "Role (e.g. QA Engineer, Developer)?", "level": "Level (TE1-TE5)?", "location": "Location (onshore / offshore)?"}[m] for m in missing]),
                     "needs_info", pending={"intent": "add", "draft": draft}, missing=missing)
    if not draft.get("associate_id"):
        return reply(f"RM-02: I can't create a {draft['level']} {draft['location']} {draft['role']} without an associate.\n1. Which associate should take this line?",
                     "needs_info", pending={"intent": "add", "draft": draft}, missing=["associate"],
                     rule_hits=[rules.hit("RM-02", "BLOCK", "A new resource cannot be created without an associate name.")])
    s, f = C.project_dates(ctx)
    rc = refs["rate_card"].get(f"{draft['level']}|{draft['location']}", {})
    months = max(1, round(((parse_iso(f) - parse_iso(s)).days + 1) / 30.4)) if s and f else 6
    tech = next((l["technology"] for l in ctx["resources"] if l.get("technology")), None)
    qty = int(draft.get("qty") or 1)
    if qty > 1:
        return reply(f"Each line needs its own associate. Add {qty} separate lines by naming {qty} associates, or add one line now.", "needs_info",
                     pending={"intent": "add", "draft": {**draft, "qty": 1}}, missing=["associate"])
    line = {"role": draft["role"], "level": draft["level"], "location": draft["location"], "technology": tech, "tier": "Tier 1" if draft["level"] in ("TE4", "TE5") else "Tier 2",
            "bill_rate": draft.get("bill_rate") or rc.get("bill_rate"), "cost_rate": rc.get("cost_rate"), "hours": draft.get("hours") or 160 * months,
            "associate_id": draft["associate_id"]}
    if line["bill_rate"] is None or line["cost_rate"] is None:
        return reply("There is no rate-card entry for that level/location. Give a bill rate and I'll add the line.", "needs_info", missing=["bill_rate"], pending={"intent": "add", "draft": draft})
    who = refs["directory"][draft["associate_id"]]["name"]
    return _ready(ctx, refs, [{"op": "add", "line": line}], f"Add a {line['level']} {line['location']} {line['role']} line for {who} (rate card: bill {line['bill_rate']}/h, cost {line['cost_rate']}/h, {line['hours']:g}h).")


def _update(ctx, refs, text):
    line = _line_ref(ctx, text)
    if not line:
        return reply("Which line? (e.g. 'update line 3 bill rate to 45')", "needs_info", missing=["line"])
    after = {}
    for fld in ("cost_rate", "bill_rate", "allocation_pct", "hours", "level", "tier", "location"):
        pat = FIELD_WORDS[fld]
        m = re.search(r"(?:" + pat + r")\s*(?:to|=|:|of|as)?\s*(\w+(?:\.\d+)?)", text, re.I)
        if m and fld not in after:
            raw = m.group(1)
            if fld == "location" and raw.lower() in ("onshore", "offshore"):
                after[fld] = raw.lower()
            elif fld in ("level",) and re.fullmatch(r"(?i)te\d", raw):
                after[fld] = raw.upper()
            elif fld == "tier":
                after[fld] = "Tier " + raw if raw.isdigit() else raw
            elif re.fullmatch(r"\d+(\.\d+)?", raw) and fld not in ("level", "location", "tier"):
                after[fld] = float(raw)
        if fld == "bill_rate" and "cost_rate" in after and after.get("cost_rate") == after.get("bill_rate"):
            after.pop("bill_rate", None)
    pct = percent(text)
    if pct and "allocation_pct" not in after and re.search(r"alloc", text, re.I):
        after["allocation_pct"] = pct
    for d, lab in labelled_dates(text, line.get("start")):
        after["start" if lab == "start" else "end"] = d
    if not after:
        return reply(f"What should I change on line {ln(ctx, line['id'])}? (rate, hours, level, location, dates, allocation)", "needs_info", missing=["change"])
    return _ready(ctx, refs, [{"op": "update", "line_id": line["id"], "after": after}], f"Update line {ln(ctx, line['id'])}: " + ", ".join(f"{k} → {v}" for k, v in after.items()) + ".")


def _release(ctx, refs, text, people):
    line = _line_ref(ctx, text)
    if not line and people:
        line = next((l for l in ctx["resources"] if l.get("associate_id") == people[0]["associate_id"]), None)
    if not line:
        return reply("Which line (or associate) should be released?", "needs_info", missing=["line"])
    ds = labelled_dates(text, line.get("start"))
    if not ds:
        return reply("Release effective which date?\n1. End date?", "needs_info", missing=["end"], pending={"intent": "release", "line_id": line["id"]})
    return _ready(ctx, refs, [{"op": "release", "line_id": line["id"], "end": ds[-1][0]}], f"Release line {ln(ctx, line['id'])} on {fmt(ds[-1][0])} (lines are end-dated, never deleted).")


def _split(ctx, refs, n, total, level, loc):
    line = next((l for l in ctx["resources"] if l["level"] == level and l["qty"] == total and not l.get("associate_id")), None) or \
        next((l for l in ctx["resources"] if l["level"] == level and l["qty"] >= n and not l.get("associate_id")), None)
    if not line:
        return reply(f"I couldn't find an unassigned {level} line with quantity {total}.", "blocked")
    rc = refs["rate_card"].get(f"{level}|{loc}", {})
    after = {"location": loc}
    if rc:
        after.update({"bill_rate": rc["bill_rate"], "cost_rate": rc["cost_rate"]})
    return _ready(ctx, refs, [{"op": "split", "line_id": line["id"], "count": n, "after": after}],
                  f"Split line {ln(ctx, line['id'])}: move {n} of {line['qty']:g} {level}s to {loc} (rate card {after.get('bill_rate', 'unchanged')}/h). The new line still needs an associate.")


def _from_structured(ctx, refs, st):
    op = st.get("op")
    if op == "assign":
        p = refs["directory"].get(st.get("associate_id"))
        if not p:
            return reply("Unknown associate.", "blocked")
        return _assign(ctx, refs, st["line_id"], p)
    if op == "add":
        return _add(ctx, refs, st["line"])
    if op in ("update", "release", "unassign", "split"):
        return _ready(ctx, refs, [st], f"{op.title()} line {ln(ctx, st.get('line_id'))}.")
    return reply("Unsupported operation.", "blocked")
