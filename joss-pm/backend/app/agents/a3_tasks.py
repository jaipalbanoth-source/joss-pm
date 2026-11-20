"""A3 - Task Builder Agent. Chat, change-only JSON. Creates / edits / deactivates tasks.
Asks for ALL missing fields in one numbered message, validates against TK-01..TK-06, returns a preview.
Stateless: the dashboard sends the project context, the message and the `pending` draft from the previous turn."""
from __future__ import annotations
import re

from .. import context as C
from .. import ops, rules
from ..dates import fmt
from ..people import find_people
from .common import labelled_dates, numbered, percent, reply, split_names, title, yes_no

ASK = {"name": "Task name?", "assignee": "Assignee?", "utilization": "Utilisation % (1-100)?", "start": "Start date?", "end": "End date?"}
FIELD_OF = {"assignee": "assignee_id", "utilization": "utilization", "start": "start", "end": "end", "name": "name"}
ADD_RE = re.compile(r"^\W*(?:please\s+|pls\s+|can you\s+|could you\s+)?(?:create|add|new|set\s*up|make|schedule|plan)\b\s*(?:an?\s+|the\s+|some\s+)?(?:new\s+)?(?P<rest>.*)$", re.I | re.S)
DEACT_RE = re.compile(r"\b(deactivate|disable|remove|delete|drop|cancel|archive)\b", re.I)
ACT_RE = re.compile(r"\b(re-?activate|activate|enable|restore)\b", re.I)
UPD_RE = re.compile(r"\b(move|extend|shorten|change|update|edit|set|push|re-?assign|rename|reduce|increase|decrease|bring|pull|shift|make|assign)\b", re.I)


def _pool_people(ctx, refs):
    pool = C.assignee_pool(ctx)
    people = list(refs["directory"].values())
    return pool, people


def _name_part(rest: str):
    q = re.findall(r"[\"“']([^\"”']{2,60})[\"”']", rest)
    if q:
        return q
    m = re.search(r"\btasks?\b\s*:?", rest, re.I)
    if m and m.start() > 0:
        part = rest[:m.start()]
    elif m:                                   # "tasks: Design, Build and Test for Priya"
        tail = rest[m.end():]
        part = re.split(r"\b(?:for|assign\w*|to|with|owned by|under)\b|\d+\s*%", tail, 1, flags=re.I)[0]
    else:
        part = re.split(r"\b(?:for|assign\w*|to|with|owned by|under|from|starting|at|by)\b|,\s*\d|\d+\s*%", rest, 1, flags=re.I)[0]
    return split_names(part)


def _extract(text, ctx, refs, ref_date):
    """Labelled fields found in free text."""
    pool, people = _pool_people(ctx, refs)
    found, ambiguous = find_people(text, people, set(pool))
    out = {"people": found, "ambiguous": ambiguous, "dates": labelled_dates(text, ref_date), "util": percent(text), "yn": yes_no(text)}
    return out


def _fmt_card(t, refs):
    who = refs["directory"].get(t.get("assignee_id"), {}).get("name", "—")
    return f"{t['name']} → {who}, {t['utilization']:g}%, {fmt(t['start'])} – {fmt(t['end'])}, Billable {'Yes' if t['billable'] else 'No'}"


def _ask(pending, text_prefix=""):
    missing = pending["missing"]
    n = len(pending["tasks"])
    qs = []
    for m in missing:
        q = ASK[m]
        if m != "name" and n > 1:
            q = q.rstrip("?") + f" (for all {n} tasks)?"
        qs.append(q)
    return reply(f"{text_prefix}I need {len(qs)} more detail{'s' if len(qs) != 1 else ''}:\n{numbered(qs)}", "needs_info", missing=missing, pending=pending)


def _suggest_assignees(ctx, refs, limit=6):
    pool = C.assignee_pool(ctx)
    return ", ".join(refs["directory"][a]["name"] for a in list(pool)[:limit] if a in refs["directory"]) or "none yet - assign associates in Resource Mgmt first"


def _validate_changes(ctx, refs, changes, extra=""):
    try:
        new, hits, new_blocks = ops.simulate(ctx, "tasks", changes, refs)
    except ops.OpError as e:
        return None, [], [rules.hit("TK-01", "BLOCK", e.message)]
    touched = {c.get("task_id") for c in changes if c.get("task_id")}
    # task ids added get fresh ids; consider all new task-related hits
    task_hits = [h for h in new_blocks]
    warns = [h for h in hits if h["level"] == "WARN" and h["module"] == "tasks" and (h["ref"] in touched or h["ref"] not in {t["id"] for t in ctx["tasks"]})]
    return new, warns, task_hits


def run(ctx: dict, refs: dict, message: str, pending: dict | None = None, structured: dict | None = None) -> dict:
    text = (message or "").strip()
    s, f = C.project_dates(ctx)
    model = refs["exec_models"].get(C.val(ctx, "execution_model") or "", {})
    bill_default = model.get("billable_default", True)

    if structured:                                   # manual form -> same checks, same preview
        t = structured["task"]
        t = {"name": t.get("name"), "assignee_id": t.get("assignee_id"), "utilization": t.get("utilization"), "start": t.get("start"),
             "end": t.get("end"), "billable": t.get("billable", bill_default), "active": t.get("active", True)}
        return _finish_add(ctx, refs, [t], bill_default)

    if re.fullmatch(r"\W*(cancel|never ?mind|forget it|discard|stop)\W*", text, re.I):
        return reply("Okay, discarded. Nothing was staged.", "info")

    existing = sorted([t for t in ctx["tasks"] if t["name"].casefold() in text.casefold()], key=lambda t: -len(t["name"]))
    # drop existing names that are substrings of longer matched names
    existing = [t for t in existing if not any(t is not o and t["name"].casefold() in o["name"].casefold() for o in existing)]

    if pending and pending.get("intent") == "add" and not (ADD_RE.match(text) and not existing and len(text.split()) > 6):
        return _answer_add(ctx, refs, text, pending, bill_default)
    if pending and pending.get("intent") == "update" and not existing:
        existing = [t for t in ctx["tasks"] if t["id"] in pending.get("task_ids", [])]
        return _update(ctx, refs, text, existing, pending)

    if existing and ACT_RE.search(text):
        return _simple_state(ctx, refs, existing, True)
    if existing and DEACT_RE.search(text) and not re.search(r"\b(change|move|extend|set)\b", text, re.I):
        return _simple_state(ctx, refs, existing, False)
    if existing and not ADD_RE.match(text):
        return _update(ctx, refs, text, existing, None)

    m = ADD_RE.match(text)
    if m and (re.search(r"\btasks?\b", text, re.I) or not existing):
        rest = m.group("rest")
        names = _name_part(rest)
        if existing and not names:
            names = [t["name"] for t in existing]
        ex = _extract(text, ctx, refs, s)
        if ex["ambiguous"] and not ex["people"]:
            tok, hits = ex["ambiguous"][0]
            opts = numbered([f"{h['name']} ({h['title']}, {h['location']})" for h in hits])
            return reply(f"'{tok.title()}' matches more than one person - which one?\n{opts}", "needs_info",
                         pending={"intent": "add", "tasks": [{"name": n, "billable": bill_default, "active": True} for n in names] or [{"billable": bill_default, "active": True}],
                                  "missing": ["assignee"], "carry": text})
        dates = ex["dates"]
        start = next((d for d, l in dates if l == "start"), None)
        end = next((d for d, l in dates if l == "end"), None)
        free = [d for d, l in dates if l is None]
        if not start and free:
            start = free.pop(0)
        if not end and free:
            end = free.pop(0)
        tasks = [{"name": n, "assignee_id": ex["people"][0]["associate_id"] if ex["people"] else None, "utilization": ex["util"],
                  "start": start, "end": end, "billable": ex["yn"] if ex["yn"] is not None else bill_default, "active": True}
                 for n in (names or [None])]
        return _finish_add(ctx, refs, tasks, bill_default)

    if pending:
        return _answer_add(ctx, refs, text, pending, bill_default)
    return reply("I can create, edit or deactivate tasks. Try: \"Create a Data Migration task for Rahul, 50% from 1 Nov to 15 Dec\", "
                 "\"Extend Data Migration to 30 Nov\" or \"Deactivate Data Migration\".", "info")


# ------------------------------------------------------------ add
def _missing(tasks):
    miss = []
    for key, fld in (("name", "name"), ("assignee", "assignee_id"), ("utilization", "utilization"), ("start", "start"), ("end", "end")):
        if any(t.get(fld) in (None, "") for t in tasks):
            miss.append(key)
    return miss


def _finish_add(ctx, refs, tasks, bill_default):
    miss = _missing(tasks)
    if miss:
        return _ask({"intent": "add", "tasks": tasks, "missing": miss},
                    "Got it" + (": " + ", ".join(t["name"] for t in tasks if t.get("name")) if any(t.get("name") for t in tasks) else "") + ". ")
    changes = [{"op": "add", "task": t} for t in tasks]
    new, warns, blocks = _validate_changes(ctx, refs, changes)
    if blocks:
        return _blocked(ctx, refs, tasks, blocks, "add")
    cards = "\n".join("• " + _fmt_card(t, refs) for t in tasks)
    util_notes = []
    for t in new["tasks"][-len(tasks):]:
        peak = rules.peak_utilisation(new, t["assignee_id"], t["start"], t["end"], t["id"], float(t["utilization"]))
        util_notes.append(f"{refs['directory'][t['assignee_id']]['name']}'s total utilisation for that period will be {peak:g}%.")
    bill_note = ""
    if bill_default is False and not any(t["billable"] for t in tasks):
        bill_note = " Project execution model is non-billable, so Billable = No."
    elif all(t["billable"] for t in tasks):
        bill_note = f" Billable defaults to Yes ({C.val(ctx, 'execution_model')})."
    txt = f"Ready. {' '.join(sorted(set(util_notes)))}{bill_note}\nReview the card{'s' if len(tasks) > 1 else ''} below and click Create.\n{cards}"
    return reply(txt, "ready", changes=changes, rule_hits=warns, preview={"kind": "tasks_add", "tasks": tasks})


def _blocked(ctx, refs, tasks, blocks, intent):
    lines = [f"{h['id']}: {h['message']}" for h in blocks]
    extra = ""
    if any(h["id"] == "TK-02" for h in blocks):
        extra = f"\nValid assignees right now: {_suggest_assignees(ctx, refs)}. Assign associates in Resource Mgmt or add them in Jade Contacts first."
    if any(h["id"] == "TK-03" for h in blocks):
        s, f = C.project_dates(ctx)
        extra += f"\nProject dates are {fmt(s)} – {fmt(f)}; pick dates inside that range and the assignee's allocation window."
    if any(h["id"] == "TK-01" and "unique" in h["message"] for h in blocks):
        extra += "\nUse a different name, or edit the existing task."
    pend = {"intent": "add", "tasks": tasks, "missing": []} if intent == "add" else None
    return reply("I can't stage that yet:\n" + "\n".join("• " + l for l in lines) + extra, "blocked", rule_hits=blocks, pending=pend)


def _answer_add(ctx, refs, text, pending, bill_default):
    """The PM replies to the numbered question list."""
    tasks = [dict(t) for t in pending["tasks"]]
    missing = list(pending.get("missing") or [])
    s, _ = C.project_dates(ctx)
    ex = _extract(text, ctx, refs, s)
    carry = pending.get("carry")
    # resolve an earlier ambiguity answered with a number / first name
    pool, people = _pool_people(ctx, refs)
    if ex["ambiguous"] and "assignee" in missing and not ex["people"]:
        tok, hits = ex["ambiguous"][0]
        return reply(f"'{tok.title()}' still matches more than one person - please use the full name:\n" + numbered([h["name"] for h in hits]), "needs_info", pending=pending, missing=missing)
    nm = re.fullmatch(r"\W*(\d)\W*", text)
    dates = ex["dates"]
    labelled = {l: d for d, l in dates if l}
    free = [d for d, l in dates if l is None]
    for key in list(missing):
        fld = FIELD_OF[key]
        val = None
        if key == "assignee" and ex["people"]:
            val = ex["people"].pop(0)["associate_id"]
        elif key == "utilization":
            val = ex["util"]
            if val is None:
                m = re.search(r"\b(\d{1,3})\b", re.sub(r"\d{1,2}\s+[A-Za-z]{3,9}|[A-Za-z]{3,9}\s+\d{1,2}", "", text))
                val = float(m.group(1)) if m and not free and not labelled else None
        elif key in ("start", "end"):
            val = labelled.pop(key, None) or (free.pop(0) if free else None)
        elif key == "name":
            cleaned = re.sub(r"\s+", " ", text).strip(" .")
            val = None if (not cleaned or len(cleaned) > 60 or labelled or free) else title(cleaned)
        if val is not None:
            for t in tasks:
                if t.get(fld) in (None, ""):
                    t[fld] = val
    yn = ex["yn"]
    if yn is not None:
        for t in tasks:
            t["billable"] = yn if re.search(r"billable", text, re.I) or "billable" in missing else t["billable"]
    return _finish_add(ctx, refs, tasks, bill_default)


# ------------------------------------------------------------ update / deactivate
def _simple_state(ctx, refs, tasks, active):
    changes = [{"op": "update" if active else "deactivate", "task_id": t["id"], **({"after": {"active": True}} if active else {})} for t in tasks]
    new, warns, blocks = _validate_changes(ctx, refs, changes)
    names = ", ".join(t["name"] for t in tasks)
    verb = "Reactivate" if active else "Deactivate"
    diff = [{"task_id": t["id"], "name": t["name"], "before": {"active": t["active"]}, "after": {"active": active}} for t in tasks]
    extra = "" if active else " (tasks are deactivated, never deleted - TK-06)"
    return reply(f"{verb} {names}{extra}? Click Update to confirm.", "ready", changes=changes, rule_hits=warns + blocks, preview={"kind": "tasks_update", "diff": diff})


def _update(ctx, refs, text, tasks, pending):
    if not tasks:
        return reply("Which task do you mean? I couldn't match a task name.", "needs_info")
    s, f = C.project_dates(ctx)
    ex = _extract(text, ctx, refs, tasks[0].get("start") or s)
    after = {}
    dates = ex["dates"]
    lbl = {l: d for d, l in dates if l}
    free = [d for d, l in dates if l is None]
    if "start" in lbl:
        after["start"] = lbl["start"]
    if "end" in lbl:
        after["end"] = lbl["end"]
    if free:
        if re.search(r"\bstart|begin", text, re.I) and "start" not in after:
            after["start"] = free.pop(0)
        elif "end" not in after:
            after["end"] = free.pop(0)
    if ex["util"] is not None:
        after["utilization"] = ex["util"]
    if ex["people"] and re.search(r"assign|reassign|give|hand|to\b|for\b", text, re.I):
        after["assignee_id"] = ex["people"][0]["associate_id"]
    if ex["yn"] is not None and re.search(r"billable", text, re.I):
        after["billable"] = ex["yn"]
    rn = re.search(r"rename\s+.+?\s+to\s+[\"“']?(.+?)[\"”']?\s*$", text, re.I)
    if rn:
        after["name"] = title(rn.group(1))
    if re.search(r"project (end|finish)|end of (the )?project", text, re.I) and f:
        after["end"] = f
    if ex["ambiguous"] and not ex["people"]:
        tok, hits = ex["ambiguous"][0]
        return reply(f"'{tok.title()}' matches more than one person - which one?\n" + numbered([h["name"] for h in hits]), "needs_info",
                     pending={"intent": "update", "task_ids": [t["id"] for t in tasks]})
    if not after:
        return reply(f"What should I change on {', '.join(t['name'] for t in tasks)}? (assignee, utilisation, start/end date, billable)", "needs_info",
                     pending={"intent": "update", "task_ids": [t["id"] for t in tasks]}, missing=["change"])
    changes = [{"op": "update", "task_id": t["id"], "after": dict(after)} for t in tasks]
    new, warns, blocks = _validate_changes(ctx, refs, changes)
    diff = [{"task_id": t["id"], "name": t["name"], "before": {k: t.get(k) for k in after}, "after": dict(after)} for t in tasks]
    if blocks:
        r = _blocked(ctx, refs, [], blocks, "update")
        r["preview"] = {"kind": "tasks_update", "diff": diff}
        return r
    desc = "; ".join(f"{k.replace('_id', '')}: {_show(refs, k, diff[0]['before'][k])} → {_show(refs, k, v)}" for k, v in after.items())
    return reply(f"Ready. {', '.join(t['name'] for t in tasks)} - {desc}.\nReview the before → after card and click Update.", "ready",
                 changes=changes, rule_hits=warns, preview={"kind": "tasks_update", "diff": diff})


def _show(refs, k, v):
    if k == "assignee_id":
        return refs["directory"].get(v, {}).get("name", "—")
    if k in ("start", "end"):
        return fmt(v)
    if k == "utilization":
        return f"{v:g}%" if v is not None else "—"
    if k == "billable":
        return "Yes" if v else "No"
    return str(v)
