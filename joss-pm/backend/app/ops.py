"""Deterministic application of change-only operations to the Project Context.
Chat agents *propose* ops; only this module applies them (after the PM clicks Create / Update)."""
from __future__ import annotations
from . import context as C
from . import rules
from .dates import parse_iso


class OpError(Exception):
    def __init__(self, message, hits=None, code="invalid"):
        super().__init__(message)
        self.message, self.hits, self.code = message, hits or [], code


def _find(items, id_, what):
    for it in items:
        if it["id"] == id_:
            return it
    raise OpError(f"{what} {id_} not found.", code="not_found")


def _date(v, label):
    if v in (None, ""):
        return None
    if parse_iso(v) is None:
        raise OpError(f"{label} must be an ISO date (YYYY-MM-DD).")
    return str(v)[:10]


# ------------------------------------------------------------------ tasks
TASK_FIELDS = {"name", "assignee_id", "billable", "active", "utilization", "start", "end"}


def apply_tasks(ctx, changes, refs):
    for ch in changes:
        op = ch.get("op")
        if op == "add":
            t = {k: ch["task"].get(k) for k in TASK_FIELDS}
            t.update({"id": C.next_id(ctx, "task", "t"), "committed": False, "has_logged_hours": False})
            t["start"], t["end"] = _date(t["start"], "Start"), _date(t["end"], "End")
            if t.get("active") is None:
                t["active"] = True
            ctx["tasks"].append(t)
        elif op == "update":
            t = _find(ctx["tasks"], ch["task_id"], "Task")
            for k, v in (ch.get("after") or {}).items():
                if k not in TASK_FIELDS:
                    raise OpError(f"Unknown task field '{k}'.")
                t[k] = _date(v, k) if k in ("start", "end") else v
        elif op == "deactivate":
            _find(ctx["tasks"], ch["task_id"], "Task")["active"] = False
        elif op == "remove":
            t = _find(ctx["tasks"], ch["task_id"], "Task")
            if t.get("committed") or t.get("has_logged_hours") or t["id"] in refs.get("logged_tasks", set()):
                raise OpError("TK-06: committed tasks / tasks with logged hours can only be deactivated, not deleted.",
                              [rules.hit("TK-06", "BLOCK", f"Task '{t['name']}' can only be deactivated.", t["id"])])
            ctx["tasks"].remove(t)
        else:
            raise OpError(f"Unknown task operation '{op}'.")


# ------------------------------------------------------------------ contacts
def apply_contacts(ctx, changes, refs):
    for ch in changes:
        op = ch.get("op")
        if op == "add":
            c = ch["contact"]
            ctx["contacts"].append({"id": C.next_id(ctx, "contact", "c"), "role": c["role"], "associate_id": c["associate_id"],
                                    "start": _date(c["start"], "Start"), "end": _date(c.get("end"), "End"),
                                    "source": c.get("source", "chat"), "committed": False})
        elif op == "update":
            c = _find(ctx["contacts"], ch["contact_id"], "Contact")
            for k, v in (ch.get("after") or {}).items():
                if k not in ("start", "end", "role", "associate_id"):
                    raise OpError(f"Unknown contact field '{k}'.")
                c[k] = _date(v, k) if k in ("start", "end") else v
            if ch.get("source"):
                c["source"] = ch["source"]
        elif op == "remove":
            c = _find(ctx["contacts"], ch["contact_id"], "Contact")
            if c.get("committed"):
                raise OpError("Committed contacts are end-dated, not removed.")
            ctx["contacts"].remove(c)
        else:
            raise OpError(f"Unknown contact operation '{op}'.")


# ------------------------------------------------------------------ resources
LINE_FIELDS = {"role", "level", "tier", "location", "technology", "qty", "bill_rate", "cost_rate", "hours", "start", "end", "allocation_pct", "associate_id"}


def _split(ctx, line, count=1):
    """Move `count` units off a multi-quantity line into a new line (same as the estimation agent)."""
    if count >= line["qty"]:
        return line
    line["qty"] = line["qty"] - count
    new = dict(line)
    new.update({"id": C.next_id(ctx, "resource", "r"), "qty": count, "associate_id": None, "source": "split", "committed": False})
    ctx["resources"].append(new)
    return new


def apply_resources(ctx, changes, refs):
    for ch in changes:
        op = ch.get("op")
        if op == "assign":
            line = _find(ctx["resources"], ch["line_id"], "Line")
            if line.get("released"):
                raise OpError(f"Line {line['id']} is released.")
            if line["qty"] > 1:
                line = _split(ctx, line, 1)
            line["associate_id"] = ch["associate_id"]
            for k in ("start", "end", "allocation_pct"):
                if ch.get(k) is not None:
                    line[k] = _date(ch[k], k) if k in ("start", "end") else ch[k]
        elif op == "unassign":
            _find(ctx["resources"], ch["line_id"], "Line")["associate_id"] = None
        elif op == "add":
            l = dict(ch["line"])
            if not l.get("associate_id"):
                raise OpError("RM-02: a new resource cannot be created without an associate name.",
                              [rules.hit("RM-02", "BLOCK", "A new resource cannot be created without an associate name.")])
            s, f = C.project_dates(ctx)
            new = {"id": C.next_id(ctx, "resource", "r"), "role": l.get("role"), "level": l.get("level"), "tier": l.get("tier", "Tier 2"),
                   "location": l.get("location"), "technology": l.get("technology"), "qty": 1, "bill_rate": l.get("bill_rate"),
                   "cost_rate": l.get("cost_rate"), "hours": l.get("hours"), "budget": 0, "associate_id": l["associate_id"],
                   "start": _date(l.get("start") or s, "Start"), "end": _date(l.get("end") or f, "End"),
                   "allocation_pct": l.get("allocation_pct", 100), "released": False, "source": "added", "committed": False}
            ctx["resources"].append(new)
        elif op == "update":
            line = _find(ctx["resources"], ch["line_id"], "Line")
            for k, v in (ch.get("after") or {}).items():
                if k not in LINE_FIELDS:
                    raise OpError(f"Unknown resource field '{k}'.")
                line[k] = _date(v, k) if k in ("start", "end") else v
        elif op == "release":
            line = _find(ctx["resources"], ch["line_id"], "Line")
            line["end"] = _date(ch["end"], "End")
            line["released"] = True
        elif op == "split":
            line = _find(ctx["resources"], ch["line_id"], "Line")
            new = _split(ctx, line, int(ch.get("count", 1)))
            for k, v in (ch.get("after") or {}).items():
                if k not in LINE_FIELDS:
                    raise OpError(f"Unknown resource field '{k}'.")
                new[k] = v
        else:
            raise OpError(f"Unknown resource operation '{op}'.")


APPLIERS = {"tasks": apply_tasks, "contacts": apply_contacts, "resources": apply_resources}
_KEY = rules.hit_key


def simulate(ctx, module, changes, refs):
    """Apply `changes` to a copy. Returns (new_ctx, hits, new_integrity_blocks)."""
    before = {_KEY(h) for h in ctx.get("open_rules") or rules.validate(ctx, refs)}
    new = C.clone(ctx)
    APPLIERS[module](new, changes, refs)
    C.recompute(new, refs)
    hits = new["open_rules"]
    new_blocks = [h for h in hits if h["level"] == "BLOCK" and h["kind"] == "integrity" and _KEY(h) not in before]
    return new, hits, new_blocks


def commit_changes(ctx, module, changes, refs):
    new, hits, new_blocks = simulate(ctx, module, changes, refs)
    if new_blocks:
        raise OpError("; ".join(h["message"] for h in new_blocks), new_blocks, code="rule_violation")
    new["saved"][module] = True
    C.recompute(new, refs)
    return new


# ------------------------------------------------------------------ edit project
def _coerce(key, value):
    typ = {f[0]: f[2] for f in C.EDIT_FIELDS}[key]
    if value in (None, ""):
        return None
    if typ == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise OpError(f"{key} must be a number.")
    if typ == "date":
        return _date(value, key)
    if typ == "yn":
        v = str(value).strip().upper()
        if v in ("Y", "YES", "TRUE"):
            return "Y"
        if v in ("N", "NO", "FALSE"):
            return "N"
        raise OpError(f"{key} must be Y or N.")
    return str(value).strip()


def edit_project(ctx, fields: dict, resolve: dict, refs, save: bool):
    new = C.clone(ctx)
    ep = new["edit_project"]
    for k, v in (fields or {}).items():
        if k not in C.EDIT_KEYS:
            raise OpError(f"Unknown field '{k}'.")
        if k in C.SYSTEM_KEYS:
            raise OpError(f"'{k}' is set by the system and cannot be edited.")
        old = ep[k]["value"]
        nv = _coerce(k, v)
        if nv != old or ep[k].get("conflict"):
            ep[k] = C.cell(nv, None, "PM", "Entered by the PM", None, "pm")
        if k == "execution_model" and nv != old:
            policy = refs["exec_models"].get(nv)
            if policy:
                for pk in ("margin_target", "tolerance_pct", "auto_timesheet_submit", "timesheet_approval"):
                    if ep[pk]["origin"] == "default" or (ep[pk]["origin"] == "sow" and ep[pk]["value"] is None):
                        ep[pk] = C.cell(policy[pk], None, f"Policy: {nv}", "Delivery-unit policy default - PM confirms.", None, "default")
    for k, pick in (resolve or {}).items():
        c = ep.get(k)
        if not c or not c.get("conflict"):
            raise OpError(f"'{k}' has no conflict to resolve.")
        key = "sow_value" if pick == "sow" else "salesforce_value" if pick == "salesforce" else None
        if not key:
            raise OpError("resolve must be 'sow' or 'salesforce'.")
        ep[k] = C.cell(c["conflict"][key], None, "PM", f"PM resolved SOW/Salesforce conflict -> {pick}", None, "pm")
    new["saved"]["edit_project"] = False
    C.recompute(new, refs)
    if save:
        blocks = [h for h in new["open_rules"] if h["module"] == "edit_project" and h["level"] == "BLOCK"]
        if not blocks:
            new["saved"]["edit_project"] = True
            C.recompute(new, refs)
        return new, blocks
    return new, []
