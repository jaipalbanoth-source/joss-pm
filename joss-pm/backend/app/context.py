"""Project Context: the draft that the PM Workspace owns (auto-saved, revisioned).
Pure functions over a dict so the agents, the rule engine and A6 all see the same shape."""
from __future__ import annotations
import copy
from .dates import parse_iso, iso
from . import clock

EDIT_FIELDS = [  # key, label, type, mandatory
    ("customer_name", "Customer name", "text", True),
    ("project_name", "Project name", "text", True),
    ("project_description", "Project description", "textarea", False),
    ("start_date", "Start date", "date", True),
    ("finish_date", "Finish date", "date", True),
    ("sales_margin", "Sales margin %", "number", False),
    ("margin_target", "Margin target %", "number", False),
    ("timesheet_approval", "Timesheet approval", "yn", False),
    ("auto_timesheet_submit", "Auto timesheet submit", "yn", False),
    ("process_status", "Project process status", "status", False),
    ("customer_project_id", "Customer project ID (PO / ref)", "text", False),
    ("tolerance_pct", "Tolerance %", "number", False),
    ("execution_model", "Execution model", "select", True),
    ("active_yn", "Active (Y/N)", "yn", False),
]
EDIT_KEYS = [f[0] for f in EDIT_FIELDS]
MANDATORY = [f[0] for f in EDIT_FIELDS if f[3]]
SYSTEM_KEYS = {"process_status", "active_yn", "sales_margin"}
MODULES = ["edit_project", "qa", "contacts", "resources", "tasks"]
MODULE_LABELS = {"edit_project": "Edit Project", "qa": "QA", "contacts": "Jade Contacts", "resources": "Resource Mgmt", "tasks": "Tasks"}
HIGH, MED = 0.85, 0.60   # confidence thresholds (decision D6 -- tune during UAT)


def cell(value=None, confidence=None, source=None, evidence=None, conflict=None, origin="sow", note=None):
    return {"value": value, "confidence": confidence, "source": source, "evidence": evidence, "conflict": conflict,
            "origin": origin, "note": note, "state": None}


def cell_state(c: dict) -> str:
    if c.get("origin") == "pm":
        return "confirmed"
    if c.get("conflict"):
        return "conflict"
    if c.get("origin") in ("system", "linked"):
        return "system"
    if c.get("origin") == "default":
        return "default" if c.get("value") is not None else "missing"
    if c.get("value") is None:
        return "missing"
    conf = c.get("confidence") or 0
    return "high" if conf >= HIGH else "review" if conf >= MED else "missing"


def new_context(project_id: str, opp: dict, sow_id: str | None, owner_email: str) -> dict:
    lines = []
    for l in opp.get("resource_lines", []):
        lines.append({"id": l["line_id"].lower(), "role": l["role"], "level": l["level"], "tier": l.get("tier"),
                      "location": l["location"], "technology": l.get("technology"), "qty": l["qty"],
                      "bill_rate": l["bill_rate"], "cost_rate": l["cost_rate"], "hours": l["hours"],
                      "budget": 0, "associate_id": None, "start": l.get("start"), "end": l.get("end"),
                      "allocation_pct": 100, "released": False, "source": "estimate", "committed": False})
    ctx = {"project_id": project_id, "opportunity_id": opp["opportunity_id"], "sow_id": sow_id,
           "sow_url": f"/api/projects/{project_id}/sow" if sow_id else None, "revision": 0, "status": "Draft",
           "owner_email": owner_email,
           "edit_project": {k: cell(origin="sow") for k in EDIT_KEYS},
           "qa": {"combination_id": None, "score": None, "overridden": False, "reason": None, "origin": None, "suggestions": [], "threshold_met": False},
           "contacts": [], "resources": lines, "tasks": [],
           "saved": {m: False for m in MODULES}, "open_rules": [], "timesheet_approver_id": None,
           "sf": {"account_name": opp["account_name"], "start_date": opp["start_date"], "end_date": opp["end_date"], "name": opp["name"]},
           "a1": None, "seq": {"contact": 0, "resource": 100, "task": 0}}
    recompute_budgets(ctx)
    ctx["baseline"] = totals(ctx)
    return ctx


def val(ctx: dict, key: str):
    return (ctx["edit_project"].get(key) or {}).get("value")


def set_val(ctx: dict, key: str, value, **kw):
    c = ctx["edit_project"][key]
    c["value"] = value
    for k, v in kw.items():
        c[k] = v


def project_dates(ctx):
    return val(ctx, "start_date"), val(ctx, "finish_date")


def line_budget(l: dict) -> float:
    return round(float(l.get("qty") or 0) * float(l.get("bill_rate") or 0) * float(l.get("hours") or 0), 2)


def line_cost(l: dict) -> float:
    return round(float(l.get("qty") or 0) * float(l.get("cost_rate") or 0) * float(l.get("hours") or 0), 2)


def recompute_budgets(ctx: dict):
    for l in ctx["resources"]:
        l["budget"] = line_budget(l)


def totals(ctx: dict) -> dict:
    b = sum(line_budget(l) for l in ctx["resources"])
    c = sum(line_cost(l) for l in ctx["resources"])
    h = sum(float(l.get("qty") or 0) * float(l.get("hours") or 0) for l in ctx["resources"])
    return {"budget": round(b, 2), "cost": round(c, 2), "hours": round(h, 2),
            "margin_pct": round((b - c) / b * 100, 1) if b else None}


def next_id(ctx: dict, kind: str, prefix: str) -> str:
    ctx["seq"][kind] += 1
    return f"{prefix}{ctx['seq'][kind]}"


def current_holder(ctx: dict, role: str, ref: str | None = None):
    """Holder of `role` on `ref` date (today); falls back to the earliest upcoming holder."""
    ref = ref or clock.today().isoformat()
    _, fin = project_dates(ctx)
    cur, upcoming = None, []
    for c in ctx["contacts"]:
        if c["role"] != role:
            continue
        end = c.get("end") or fin or "9999-12-31"
        if c["start"] <= ref <= end:
            cur = c
        elif c["start"] > ref:
            upcoming.append(c)
    if cur:
        return cur
    return sorted(upcoming, key=lambda c: c["start"])[0] if upcoming else None


def _lo(a, b):
    xs = [x for x in (a, b) if x]
    return min(xs) if xs else None


def _hi(a, b):
    xs = [x for x in (a, b) if x]
    return max(xs) if xs else None


def assignee_pool(ctx: dict) -> dict:
    """{associate_id: {"start","end","allocation_pct","via":[...]}} -- who may be given tasks (TK-02/TK-03)."""
    s, f = project_dates(ctx)
    pool = {}

    def add(aid, a, b, pct, via):
        a, b = a or s, b or f
        p = pool.get(aid)
        if not p:
            pool[aid] = {"start": a, "end": b, "allocation_pct": pct, "via": [via]}
        else:
            p["start"], p["end"] = _lo(p["start"], a), _hi(p["end"], b)
            p["allocation_pct"] = max(p["allocation_pct"], pct)
            p["via"].append(via)

    for l in ctx["resources"]:
        if l.get("associate_id"):
            add(l["associate_id"], l.get("start"), l.get("end"), l.get("allocation_pct") or 100, "resource")
    for c in ctx["contacts"]:
        add(c["associate_id"], c.get("start"), c.get("end"), 100, c["role"])
    return pool


def derive_status(ctx: dict, hits: list) -> str:
    if ctx["status"] in ("Active", "On Hold", "Closed"):
        return ctx["status"]
    if not ctx["saved"]["edit_project"]:
        return "Draft"
    blocks = [h for h in hits if h["level"] == "BLOCK"]
    if all(ctx["saved"].values()) and not blocks:
        return "Ready to Submit"
    return "In Setup"


def recompute(ctx: dict, refs: dict) -> dict:
    """Derived values (X-03 approver, sales margin from estimate), field states, open rules and status."""
    from . import rules
    recompute_budgets(ctx)
    t = totals(ctx)
    if t["margin_pct"] is not None:
        set_val(ctx, "sales_margin", t["margin_pct"], confidence=1.0, origin="linked", source="Resource Mgmt (estimate lines)",
                evidence=f"(Budget {t['budget']:,.0f} - cost {t['cost']:,.0f}) / budget", conflict=None)
    pm = current_holder(ctx, "Project Manager")
    ctx["timesheet_approver_id"] = pm["associate_id"] if pm else None
    today = clock.today().isoformat()
    s, f = project_dates(ctx)
    if ctx["status"] == "Active":
        set_val(ctx, "active_yn", "Y" if (s and f and s <= today <= f) else "N", origin="system", confidence=None)
    else:
        set_val(ctx, "active_yn", "N", origin="system", confidence=None)
    set_val(ctx, "process_status", ctx["status"], origin="system", confidence=None)
    hits = rules.validate(ctx, refs)
    ctx["open_rules"] = hits
    new_status = derive_status(ctx, hits)
    ctx["status"] = new_status
    set_val(ctx, "process_status", new_status, origin="system", confidence=None)
    for c in ctx["edit_project"].values():
        c["state"] = cell_state(c)
    ctx["totals"] = t
    return ctx


def clone(ctx):
    return copy.deepcopy(ctx)
