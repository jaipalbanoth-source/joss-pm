"""The JOSS rulebook (design section 07). One engine, enforced twice: by each chat agent while the PM works
and again by A6 at submit.  Level BLOCK stops Create/Submit; WARN lets the PM continue.
`kind`: 'integrity'  -> an operation that introduces the hit is rejected
        'completeness' -> the draft may exist, but Submit is blocked until it is fixed."""
from __future__ import annotations
from .dates import fmt, overlaps
from . import context as C
from . import clock

RULES = [  # id, module, level, text
    ("EP-00", "edit_project", "BLOCK", "Mandatory header fields (customer, project name, dates, execution model) are filled in  [added]"),
    ("EP-01", "edit_project", "BLOCK", "Finish date is on or after the start date"),
    ("EP-02", "edit_project", "BLOCK", "Customer exists in the JOSS customer master (or matches the Salesforce Account)"),
    ("EP-03", "edit_project", "BLOCK/WARN", "Margins between 0 and 100% (BLOCK); sales margin below margin target (WARN)"),
    ("EP-04", "edit_project", "BLOCK", "Tolerance % between 0 and 100"),
    ("EP-05", "edit_project", "BLOCK", "Execution model is from the JOSS allowed list"),
    ("EP-06", "edit_project", "BLOCK", "Active and process status agree (Active = N cannot have status Active once the project has started)"),
    ("EP-07", "edit_project", "BLOCK", "Project name is unique for the customer"),
    ("QA-01", "qa", "BLOCK", "Exactly one combination selected, and it exists in the QA master"),
    ("JC-01", "contacts", "BLOCK", "A single-holder role has at most one holder on any date"),
    ("JC-02", "contacts", "BLOCK", "Contact dates are within the project dates"),
    ("JC-03", "contacts", "AUTO", "Handover: previous holder end date = new start - 1 day"),
    ("JC-04", "contacts", "BLOCK", "Associate exists in the directory and is active"),
    ("JC-05", "contacts", "BLOCK", "Project has a Project Manager at submit"),
    ("RM-01", "resources", "BLOCK", "Every resource line has an associate"),
    ("RM-02", "resources", "BLOCK", "A new resource cannot be created without an associate name"),
    ("RM-03", "resources", "WARN", "Associate allocation across projects <= 100%"),
    ("RM-04", "resources", "BLOCK", "Line dates within the project dates; budget = quantity x bill rate (x hours), recomputed"),
    ("RM-05", "resources", "WARN", "Budget variance vs estimate is above tolerance %"),
    ("RM-06", "resources", "BLOCK", "A line with an associate has quantity 1 (split lines first)  [added]"),
    ("TK-01", "tasks", "BLOCK", "All 7 task fields present; task name unique within the project"),
    ("TK-02", "tasks", "BLOCK", "Assignee is in the Resource Mgmt associate list or is a Jade Contact role holder"),
    ("TK-03", "tasks", "BLOCK", "Task dates within the project and the assignee's allocation window"),
    ("TK-04", "tasks", "BLOCK/WARN", "Utilisation 1-100 (BLOCK); overlapping tasks per assignee <= their allocation (WARN)"),
    ("TK-05", "tasks", "BLOCK", "Non-billable execution model means Billable = N"),
    ("TK-06", "tasks", "BLOCK", "Tasks with logged hours can only be deactivated, not deleted"),
    ("X-01", "submit", "BLOCK", "Submission is idempotent on submission_id; an out-of-date revision is rejected"),
    ("X-02", "submit", "BLOCK", "All 5 modules saved and free of blocking rules before submit"),
    ("X-03", "submit", "AUTO", "Timesheet approver = current Project Manager"),
    ("X-04", "submit", "BLOCK", "Only the project's PM (or delegate) can submit changes"),
    ("X-05", "submit", "AUTO", "Writes follow the order header > QA > contacts > resources > tasks"),
    ("X-06", "edit_project", "BLOCK", "SOW values that conflict with Salesforce are resolved by the PM before submit"),
]
MODULE_OF = {"EP": "edit_project", "X-06": "edit_project", "QA": "qa", "JC": "contacts", "RM": "resources", "TK": "tasks", "X-0": "submit"}


def module_of(rule_id: str) -> str:
    if rule_id == "X-06":
        return "edit_project"
    return MODULE_OF.get(rule_id.split("-")[0], MODULE_OF.get(rule_id[:3], "submit"))


def hit(rid, level, message, ref=None, kind="integrity", module=None):
    return {"id": rid, "level": level, "module": module or module_of(rid), "message": message, "ref": ref, "kind": kind}


def hit_key(h):
    return (h["id"], h.get("ref"), h["message"])


def _name(refs, aid):
    a = refs["directory"].get(aid)
    return a["name"] if a else (aid or "?")


def validate(ctx: dict, refs: dict, scope: str = "draft") -> list[dict]:
    H = []
    ep = ctx["edit_project"]
    v = lambda k: C.val(ctx, k)
    start, fin = v("start_date"), v("finish_date")

    # ---------------- Edit Project
    for k in C.MANDATORY:
        if v(k) in (None, ""):
            label = dict((f[0], f[1]) for f in C.EDIT_FIELDS)[k]
            H.append(hit("EP-00", "BLOCK", f"{label} is required.", k, "completeness"))
    if start and fin and fin < start:
        H.append(hit("EP-01", "BLOCK", f"Finish date {fmt(fin)} is before start date {fmt(start)}.", "finish_date"))
    cust = v("customer_name")
    if cust:
        known = {c.casefold() for c in refs["customers"]} | {(ctx["sf"]["account_name"] or "").casefold()}
        if cust.casefold() not in known:
            H.append(hit("EP-02", "BLOCK", f"Customer '{cust}' is not in the JOSS customer master and does not match the Salesforce Account.", "customer_name"))
    for k in ("sales_margin", "margin_target"):
        x = v(k)
        if x is not None and not (0 <= float(x) <= 100):
            H.append(hit("EP-03", "BLOCK", f"{k.replace('_', ' ').title()} must be between 0 and 100%.", k))
    sm, mt = v("sales_margin"), v("margin_target")
    if sm is not None and mt is not None and 0 <= float(sm) <= 100 and float(sm) < float(mt):
        H.append(hit("EP-03", "WARN", f"Sales margin {sm}% is below the margin target {mt}%.", "sales_margin"))
    tol = v("tolerance_pct")
    if tol is not None and not (0 <= float(tol) <= 100):
        H.append(hit("EP-04", "BLOCK", "Tolerance % must be between 0 and 100.", "tolerance_pct"))
    em = v("execution_model")
    if em and em not in refs["exec_models"]:
        H.append(hit("EP-05", "BLOCK", f"Execution model '{em}' is not in the JOSS allowed list ({', '.join(refs['exec_models'])}).", "execution_model"))
    today = clock.today().isoformat()
    if ctx["status"] == "Active" and v("active_yn") == "N" and start and fin and start <= today <= fin:
        H.append(hit("EP-06", "BLOCK", "Active = N cannot have process status Active while the project is within its dates.", "active_yn"))
    if cust and v("project_name") and (cust.casefold(), v("project_name").casefold()) in refs["other_names"]:
        H.append(hit("EP-07", "BLOCK", f"Project name '{v('project_name')}' already exists for {cust}.", "project_name"))
    for k, c in ep.items():
        if c.get("conflict"):
            cf = c["conflict"]
            H.append(hit("X-06", "BLOCK", f"{k.replace('_', ' ').title()}: SOW says {cf.get('sow_value')} but Salesforce says {cf.get('salesforce_value')} - PM must pick one.", k, "completeness"))

    # ---------------- QA
    qa = ctx["qa"]
    if not qa.get("combination_id"):
        H.append(hit("QA-01", "BLOCK", "Select exactly one QA project-type combination.", None, "completeness"))
    elif qa["combination_id"] not in refs["qa"]:
        H.append(hit("QA-01", "BLOCK", f"{qa['combination_id']} does not exist in the QA master.", qa["combination_id"]))

    # ---------------- Jade Contacts
    contacts = ctx["contacts"]
    for c in contacts:
        a = refs["directory"].get(c["associate_id"])
        ref = c["id"]
        if not a:
            H.append(hit("JC-04", "BLOCK", f"Associate {c['associate_id']} does not exist in the directory.", ref))
        elif a["status"] != "active":
            H.append(hit("JC-04", "BLOCK", f"{a['name']} is not an active employee.", ref))
        s, e = c["start"], c.get("end")
        if e and e < s:
            H.append(hit("JC-02", "BLOCK", f"{c['role']} {_name(refs, c['associate_id'])}: end {fmt(e)} is before start {fmt(s)}.", ref))
        if start and s < start:
            H.append(hit("JC-02", "BLOCK", f"{c['role']} {_name(refs, c['associate_id'])} starts {fmt(s)}, before the project start {fmt(start)}.", ref))
        if fin and ((e and e > fin) or s > fin):
            H.append(hit("JC-02", "BLOCK", f"{c['role']} {_name(refs, c['associate_id'])} runs past the project finish {fmt(fin)}.", ref))
    for role, single in refs["roles"].items():
        if not single:
            continue
        rows = [c for c in contacts if c["role"] == role]
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if overlaps(a["start"], a.get("end") or fin, b["start"], b.get("end") or fin):
                    H.append(hit("JC-01", "BLOCK",
                                 f"{role} is single-holder but {_name(refs, a['associate_id'])} ({fmt(a['start'])}-{fmt(a.get('end')) if a.get('end') else 'open'}) "
                                 f"overlaps {_name(refs, b['associate_id'])} ({fmt(b['start'])}-{fmt(b.get('end')) if b.get('end') else 'open'}).", f"{a['id']},{b['id']}"))
    if not any(c["role"] == "Project Manager" for c in contacts):
        H.append(hit("JC-05", "BLOCK", "The project needs a Project Manager.", None, "completeness"))

    # ---------------- Resources
    pool_alloc = {}
    for l in ctx["resources"]:
        ref = l["id"]
        if not l.get("associate_id"):
            H.append(hit("RM-01", "BLOCK", f"Line {l['id']} ({l['role']} {l['level']} {l['location']}) has no associate.", ref, "completeness"))
        else:
            a = refs["directory"].get(l["associate_id"])
            if not a or a["status"] != "active":
                H.append(hit("JC-04", "BLOCK", f"Line {l['id']}: associate {l['associate_id']} is missing or inactive.", ref, module="resources"))
            if float(l.get("qty") or 0) != 1:
                H.append(hit("RM-06", "BLOCK", f"Line {l['id']} has an associate but quantity {l.get('qty')}; split it first.", ref))
            pool_alloc[l["associate_id"]] = pool_alloc.get(l["associate_id"], 0) + (l.get("allocation_pct") or 100)
        s, e = l.get("start"), l.get("end")
        if (start and s and s < start) or (fin and e and e > fin) or (s and e and e < s):
            H.append(hit("RM-04", "BLOCK", f"Line {l['id']} dates {fmt(s)}-{fmt(e)} are outside the project dates {fmt(start)}-{fmt(fin)}.", ref))
    for aid, pct in pool_alloc.items():
        a = refs["directory"].get(aid)
        total = pct + (a["other_allocation_pct"] if a else 0)
        if total > 100:
            H.append(hit("RM-03", "WARN", f"{_name(refs, aid)} would be allocated {total}% across projects ({a['other_allocation_pct']}% elsewhere + {pct}% here).", aid))
    base, cur = ctx.get("baseline", {}).get("budget"), C.totals(ctx)["budget"]
    if base and tol is not None:
        var = abs(cur - base) / base * 100
        if var > float(tol):
            H.append(hit("RM-05", "WARN", f"Budget {cur:,.0f} differs from the estimate {base:,.0f} by {var:.1f}% (tolerance {tol}%).", None))

    # ---------------- Tasks
    pool = C.assignee_pool(ctx)
    model = refs["exec_models"].get(em or "", {})
    names = {}
    for t in ctx["tasks"]:
        H.extend(validate_task(ctx, refs, t, pool, model, names))
    committed_logged = refs.get("logged_tasks", set())
    present = {t["id"] for t in ctx["tasks"]}
    for lid in committed_logged:
        if lid not in present:
            H.append(hit("TK-06", "BLOCK", f"Task {lid} has logged timesheet hours and cannot be deleted; deactivate it instead.", lid))

    if scope == "submit":
        for m in C.MODULES:
            if not ctx["saved"].get(m):
                H.append(hit("X-02", "BLOCK", f"Module '{C.MODULE_LABELS[m]}' has not been saved.", m, "completeness", module="submit"))
    # de-duplicate
    seen, out = set(), []
    for h in H:
        k = hit_key(h)
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def validate_task(ctx, refs, t, pool, model, names) -> list[dict]:
    H = []
    ref = t["id"]
    s, f = C.project_dates(ctx)
    missing = [k for k in ("name", "assignee_id", "utilization", "start", "end") if t.get(k) in (None, "")]
    if t.get("billable") not in (True, False):
        missing.append("billable")
    if t.get("active") not in (True, False):
        missing.append("active")
    if missing:
        H.append(hit("TK-01", "BLOCK", f"Task '{t.get('name') or ref}' is missing: {', '.join(missing)}.", ref))
    n = (t.get("name") or "").strip().casefold()
    if n:
        if n in names:
            H.append(hit("TK-01", "BLOCK", f"Task name '{t['name']}' is not unique within the project.", ref))
        names[n] = ref
    aid = t.get("assignee_id")
    who = refs["directory"].get(aid, {}).get("name", aid)
    if aid:
        if aid not in pool:
            H.append(hit("TK-02", "BLOCK", f"{who} is not in the project's resource list or Jade Contacts, so cannot be assigned '{t.get('name')}'.", ref))
        else:
            w = pool[aid]
            if t.get("start") and w["start"] and t["start"] < w["start"] or t.get("end") and w["end"] and t["end"] > w["end"]:
                H.append(hit("TK-03", "BLOCK", f"'{t.get('name')}' ({fmt(t.get('start'))}-{fmt(t.get('end'))}) is outside {who}'s allocation window "
                             f"({fmt(w['start'])}-{fmt(w['end'])}).", ref))
    if (t.get("start") and s and t["start"] < s) or (t.get("end") and f and t["end"] > f):
        H.append(hit("TK-03", "BLOCK", f"'{t.get('name')}' dates are outside the project dates {fmt(s)}-{fmt(f)}.", ref))
    if t.get("start") and t.get("end") and t["end"] < t["start"]:
        H.append(hit("TK-03", "BLOCK", f"'{t.get('name')}' ends before it starts.", ref))
    u = t.get("utilization")
    if u is not None and not (1 <= float(u) <= 100):
        H.append(hit("TK-04", "BLOCK", f"Utilisation {u}% must be between 1 and 100.", ref))
    elif u is not None and aid in pool and t.get("active", True) and t.get("start") and t.get("end"):
        peak = peak_utilisation(ctx, aid, t["start"], t["end"], t.get("id"), float(u))
        alloc = pool[aid]["allocation_pct"]
        if peak > alloc:
            H.append(hit("TK-04", "WARN", f"{who}'s total utilisation for that period will be {peak:g}%, above their {alloc:g}% allocation.", ref))
    if model and model.get("billable_default") is False and t.get("billable") is True:
        H.append(hit("TK-05", "BLOCK", f"Execution model {C.val(ctx, 'execution_model')} is non-billable, so Billable must be N.", ref))
    return H


def peak_utilisation(ctx, aid, start, end, exclude_id, own) -> float:
    """Highest concurrent utilisation (this task + the assignee's other active tasks) inside [start, end]."""
    others = [t for t in ctx["tasks"] if t.get("assignee_id") == aid and t.get("active", True) and t["id"] != exclude_id
              and t.get("start") and t.get("end") and overlaps(t["start"], t["end"], start, end)]
    points = {start} | {max(start, t["start"]) for t in others}
    peak = 0.0
    for p in points:
        tot = own + sum(float(t["utilization"] or 0) for t in others if t["start"] <= p <= t["end"])
        peak = max(peak, tot)
    return peak


def summarize(hits):
    return {"block": sum(1 for h in hits if h["level"] == "BLOCK"), "warn": sum(1 for h in hits if h["level"] == "WARN")}


def module_status(ctx, hits) -> dict:
    out = {}
    for m in C.MODULES:
        hs = [h for h in hits if h["module"] == m]
        out[m] = {"label": C.MODULE_LABELS[m], "saved": bool(ctx["saved"].get(m)), "blocks": sum(1 for h in hs if h["level"] == "BLOCK"),
                  "warns": sum(1 for h in hs if h["level"] == "WARN")}
        out[m]["ready"] = out[m]["saved"] and out[m]["blocks"] == 0
    return out
