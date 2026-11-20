"""Application service layer: project lifecycle, revisions, audit, agent orchestration."""
from __future__ import annotations
import uuid

from . import clock, context as C, db, masters, ops, rules
from .agents import a1_sow, a2_qa, a3_tasks, a4_contacts, a5_resources, a6_commit
from .db import jd, jl
from .joss_writer import SimulatedJossWriter


class ApiError(Exception):
    def __init__(self, status: int, message: str, hits=None, extra=None):
        super().__init__(message)
        self.status, self.message, self.hits, self.extra = status, message, hits or [], extra or {}


# ------------------------------------------------------------------ audit / revisions
def audit(actor, project_id, action, module=None, detail=None):
    db.run("INSERT INTO audit_log(ts,actor,project_id,action,module,detail) VALUES(?,?,?,?,?,?)",
           (clock.now(), actor, project_id, action, module, jd(detail or {})))


def _row(project_id):
    r = db.one("SELECT * FROM projects WHERE project_id=?", (project_id,))
    if not r:
        raise ApiError(404, f"Project {project_id} not found")
    return r


def load(project_id: str) -> tuple[dict, dict]:
    r = _row(project_id)
    ctx = jl(r["context"])
    ctx["revision"] = r["revision"]
    ctx["committed_revision"] = r["committed_revision"]
    return ctx, r


def save(project_id: str, ctx: dict, expected_revision: int | None, actor: str, note: str) -> dict:
    """Optimistic-concurrency save: revision + 1, snapshot kept for history."""
    r = _row(project_id)
    if expected_revision is not None and expected_revision != r["revision"]:
        raise ApiError(409, f"Out-of-date revision {expected_revision}; current is {r['revision']}. Reload.")
    rev = r["revision"] + 1
    ctx["revision"] = rev
    ctx.pop("committed_revision", None)
    blob = jd(ctx)
    db.run("UPDATE projects SET context=?, revision=?, status=? WHERE project_id=?", (blob, rev, ctx["status"], project_id))
    db.run("INSERT INTO context_revisions VALUES(?,?,?,?,?,?)", (project_id, rev, blob, actor, clock.now(), note))
    ctx["committed_revision"] = r["committed_revision"]
    return ctx


def _expect(ctx_row, expected):
    if expected is not None and expected != ctx_row["revision"]:
        raise ApiError(409, f"Out-of-date revision {expected}; current is {ctx_row['revision']}. Reload.")


# ------------------------------------------------------------------ project lifecycle
def next_project_id() -> str:
    r = db.one("SELECT project_id FROM projects ORDER BY project_id DESC LIMIT 1")
    n = int(r["project_id"].split("-")[1]) + 1 if r else 24817
    return f"JOSS-{n}"


def create_project(opportunity_id: str, actor: str) -> dict:
    opp = masters.opportunity(opportunity_id)
    if not opp:
        raise ApiError(404, "Salesforce opportunity not found")
    if db.one("SELECT 1 x FROM projects WHERE opportunity_id=?", (opportunity_id,)):
        raise ApiError(409, "A JOSS project already exists for this opportunity")
    pid = next_project_id()
    ctx = C.new_context(pid, opp, opp["sow_id"], actor)
    db.run("INSERT INTO projects(project_id,opportunity_id,owner_email,delegates,created_at,revision,status,context) VALUES(?,?,?,?,?,?,?,?)",
           (pid, opportunity_id, actor, "[]", clock.now(), 0, "Draft", jd(ctx)))
    audit(actor, pid, "project.created", None, {"opportunity_id": opportunity_id, "sow_id": opp["sow_id"]})
    refs = masters.load_refs(pid)
    if opp["sow_id"]:
        _run_a1(ctx, opp, refs)
        _run_a2(ctx, refs, auto=True)
        audit("agent:A1", pid, "a1.extracted", "edit_project", {"warnings": ctx["a1"]["warnings"]})
    else:
        ctx["a1"] = {"qa_signals": None, "warnings": [], "errors": ["No SOW attached - upload the SOW or fill the form manually."]}
    C.recompute(ctx, refs)
    return save(pid, ctx, None, actor, "Project created" + (" - A1 pre-filled Edit Project from the SOW" if opp["sow_id"] else " (no SOW attached)"))


def _run_a1(ctx, opp, refs, sow=None, keep_pm_edits=True):
    sow = sow or masters.sow(ctx.get("sow_id"))
    out = a1_sow.run({"project_id": ctx["project_id"], "sow_text": sow["text"] if sow else "", "opportunity": opp,
                      "customers": refs["customers"], "exec_models": refs["exec_models"]})
    ctx["sow_id"] = sow["sow_id"] if sow else ctx.get("sow_id")
    ctx["sow_url"] = f"/api/projects/{ctx['project_id']}/sow" if sow else None
    if out["errors"]:
        ctx["a1"] = {"qa_signals": None, "warnings": out["warnings"], "errors": out["errors"]}
        return out, []
    return out, a1_sow.merge_into_context(ctx, out, keep_pm_edits)


def _run_a2(ctx, refs, auto=False, actor="agent:A2"):
    signals = (ctx.get("a1") or {}).get("qa_signals")
    if not signals:
        return None
    out = a2_qa.run({"project_id": ctx["project_id"], "qa_signals": signals, "execution_model": ctx["edit_project"]["execution_model"],
                     "qa_master": list(refs["qa"].values())})
    q = ctx["qa"]
    q["suggestions"] = out["top3"]
    q["best_score"] = out["best_score"]
    q["warnings"] = out["warnings"]
    q["threshold_met"] = out["preselect"] is not None
    if q.get("origin") != "pm" and out["preselect"]:
        top = out["top3"][0]
        q.update({"combination_id": out["preselect"], "score": top["score"], "overridden": False, "reason": None, "origin": "agent"})
    return out


def rerun_sow(project_id: str, actor: str, sow_id=None, filename=None, text=None, keep_pm_edits=True) -> dict:
    ctx, row = load(project_id)
    opp = masters.opportunity(ctx["opportunity_id"])
    refs = masters.load_refs(project_id)
    sow = None
    if text is not None:
        new_id = f"SOW-{uuid.uuid4().hex[:8].upper()}"
        db.run("INSERT INTO sows VALUES(?,?,?,?,?)", (new_id, filename or "uploaded.txt", text, "uploaded", clock.now()))
        sow = masters.sow(new_id)
        audit(actor, project_id, "sow.replaced", "edit_project", {"sow_id": new_id, "filename": filename})
    out, changed = _run_a1(ctx, opp, refs, sow, keep_pm_edits)
    if not out["errors"]:
        _run_a2(ctx, refs)
    C.recompute(ctx, refs)
    audit("agent:A1", project_id, "a1.extracted", "edit_project", {"changed": changed, "warnings": out["warnings"], "errors": out["errors"]})
    return save(project_id, ctx, None, actor, f"A1 re-run ({len(changed)} fields changed)")


def get_view(project_id: str) -> dict:
    ctx, row = load(project_id)
    refs = masters.load_refs(project_id)
    C.recompute(ctx, refs)
    hits = ctx["open_rules"]
    submit_hits = rules.validate(ctx, refs, scope="submit")
    mods = rules.module_status(ctx, submit_hits)
    return {"context": ctx, "modules": mods, "submit_hits": submit_hits, "hits_summary": rules.summarize(submit_hits),
            "owner_email": row["owner_email"], "delegates": jl(row["delegates"]), "committed_revision": row["committed_revision"],
            "pending_changes": row["committed_revision"] is not None and row["revision"] > row["committed_revision"],
            "pool": C.assignee_pool(ctx), "ready": ctx["status"] == "Ready to Submit"}


def delete_project(project_id, actor):
    ctx, row = load(project_id)
    if row["committed_revision"] is not None:
        raise ApiError(409, "A committed project cannot be deleted.")
    for t in ("projects", "context_revisions", "chat_log", "qa_overrides"):
        db.run(f"DELETE FROM {t} WHERE project_id=?", (project_id,))
    audit(actor, project_id, "project.deleted")


# ------------------------------------------------------------------ edit project / qa / modules
def update_edit_project(project_id, fields, resolve, save_flag, expected_revision, actor):
    ctx, row = load(project_id)
    _expect(row, expected_revision)
    refs = masters.load_refs(project_id)
    try:
        new, blocks = ops.edit_project(ctx, fields, resolve, refs, save_flag)
    except ops.OpError as e:
        raise ApiError(422, e.message, e.hits)
    ran_a2 = False
    if save_flag and new["saved"]["edit_project"]:
        _run_a2(new, refs)                  # trigger: Edit Project draft saved
        ran_a2 = True
        C.recompute(new, refs)
    audit(actor, project_id, "edit_project.saved" if save_flag else "edit_project.edited", "edit_project", {"fields": list((fields or {}).keys()), "resolved": resolve or {}})
    out = save(project_id, new, expected_revision, actor, "Edit Project " + ("saved" if save_flag and not blocks else "edited"))
    return {"context": out, "blocks": blocks, "a2_ran": ran_a2}


def select_qa(project_id, combination_id, reason, expected_revision, actor):
    ctx, row = load(project_id)
    _expect(row, expected_revision)
    refs = masters.load_refs(project_id)
    if combination_id not in refs["qa"]:
        raise ApiError(422, f"QA-01: {combination_id} does not exist in the QA master.")
    q = ctx["qa"]
    suggested = (q.get("suggestions") or [{}])[0].get("combination_id")
    sug = next((s for s in q.get("suggestions") or [] if s["combination_id"] == combination_id), None)
    overridden = bool(suggested) and combination_id != suggested
    if overridden and not (reason or "").strip():
        raise ApiError(422, "Please give a short reason for overriding the suggested combination.")
    q.update({"combination_id": combination_id, "score": sug["score"] if sug else None, "overridden": overridden,
              "reason": (reason or "").strip() or None, "origin": "pm"})
    if overridden:
        db.run("INSERT INTO qa_overrides(project_id,suggested,chosen,reason,ts,actor) VALUES(?,?,?,?,?,?)",
               (project_id, suggested, combination_id, reason, clock.now(), actor))
    ctx["saved"]["qa"] = True
    C.recompute(ctx, refs)
    audit(actor, project_id, "qa.selected", "qa", {"combination_id": combination_id, "overridden": overridden, "reason": reason})
    return save(project_id, ctx, expected_revision, actor, f"QA set to {combination_id}" + (" (override)" if overridden else ""))


def save_module(project_id, module, expected_revision, actor):
    if module not in C.MODULES:
        raise ApiError(404, "Unknown module")
    ctx, row = load(project_id)
    _expect(row, expected_revision)
    refs = masters.load_refs(project_id)
    C.recompute(ctx, refs)
    blocks = [h for h in ctx["open_rules"] if h["module"] == module and h["level"] == "BLOCK"]
    if blocks:
        raise ApiError(422, f"{C.MODULE_LABELS[module]} still has {len(blocks)} blocking rule(s).", blocks)
    ctx["saved"][module] = True
    C.recompute(ctx, refs)
    audit(actor, project_id, "module.saved", module)
    return save(project_id, ctx, expected_revision, actor, f"{C.MODULE_LABELS[module]} marked complete")


# ------------------------------------------------------------------ chat agents
AGENTS = {"tasks": a3_tasks, "contacts": a4_contacts, "resources": a5_resources}


def log_chat(project_id, module, role, content, payload=None):
    db.run("INSERT INTO chat_log(project_id,module,role,content,payload,ts) VALUES(?,?,?,?,?,?)", (project_id, module, role, content, jd(payload or {}), clock.now()))


def chat_history(project_id, module):
    return [{**r, "payload": jl(r["payload"])} for r in db.rows("SELECT * FROM chat_log WHERE project_id=? AND module=? ORDER BY id", (project_id, module))]


def chat(project_id, module, message, pending, structured, actor):
    if module == "qa":
        ctx, _ = load(project_id)
        refs = masters.load_refs(project_id)
        res = a2_qa.chat(message, list(refs["qa"].values()), ctx["qa"].get("combination_id"))
        log_chat(project_id, "qa", "user", message)
        log_chat(project_id, "qa", "agent", res["reply"], res)
        return res
    if module not in AGENTS:
        raise ApiError(404, "Unknown chat module")
    ctx, row = load(project_id)
    refs = masters.load_refs(project_id)
    C.recompute(ctx, refs)
    if not (C.val(ctx, "start_date") and C.val(ctx, "finish_date")):
        raise ApiError(422, "Set the project start and finish dates in Edit Project first (every date is checked against them).")
    res = AGENTS[module].run(ctx, refs, message, pending, structured)
    res["revision"] = row["revision"]
    log_chat(project_id, module, "user", message or "(form)", {"structured": structured})
    log_chat(project_id, module, "agent", res["reply"], {k: res[k] for k in ("status", "changes", "preview", "rule_hits", "missing", "pending")})
    return res


def apply_changes(project_id, module, changes, expected_revision, actor):
    if module not in AGENTS:
        raise ApiError(404, "Unknown module")
    ctx, row = load(project_id)
    _expect(row, expected_revision)
    refs = masters.load_refs(project_id)
    try:
        new = ops.commit_changes(ctx, module, changes, refs)
    except ops.OpError as e:
        raise ApiError(422, e.message, e.hits)
    audit(actor, project_id, f"{module}.changed", module, {"changes": changes})
    log_chat(project_id, module, "system", f"{len(changes)} change(s) applied by {actor}", {"changes": changes})
    return save(project_id, new, expected_revision, actor, f"{C.MODULE_LABELS[module]}: {len(changes)} change(s) applied")


# ------------------------------------------------------------------ submit
def build_package(project_id, actor):
    ctx, row = load(project_id)
    refs = masters.load_refs(project_id)
    C.recompute(ctx, refs)
    return {"project_id": project_id, "revision": row["revision"], "context": ctx, "submitter": actor,
            "modules": {"project": {k: C.val(ctx, k) for k in C.EDIT_KEYS}, "qa": ctx["qa"], "contacts": ctx["contacts"],
                        "resources": ctx["resources"], "tasks": ctx["tasks"]}}, row, refs


def submit(project_id, submission_id, expected_revision, fail_at, actor):
    pkg, row, refs = build_package(project_id, actor)
    pkg["submission_id"] = submission_id or f"sub-{uuid.uuid4().hex[:8]}"
    if expected_revision is not None:
        pkg["revision"] = expected_revision
    prior = db.one("SELECT * FROM submissions WHERE submission_id=?", (pkg["submission_id"],))
    if prior:
        prior["result"] = jl(prior["result"])
        if prior["project_id"] != project_id:
            raise ApiError(409, "submission_id belongs to another project")
    result = a6_commit.run(pkg, refs, SimulatedJossWriter(fail_at), current_revision=row["revision"], submitter=actor,
                           owner=row["owner_email"], delegates=jl(row["delegates"]), prior=prior)
    if result.get("idempotent_replay"):
        audit("agent:A6", project_id, "commit.replayed", "submit", {"submission_id": pkg["submission_id"]})
        return result
    status = result["overall_status"]
    db.run("INSERT OR REPLACE INTO submissions VALUES(?,?,?,?,?,?)", (pkg["submission_id"], project_id, pkg["revision"], status, jd(result), clock.now()))
    audit("agent:A6", project_id, f"commit.{status}", "submit", {"submission_id": pkg["submission_id"], "result": result, "submitted_by": actor})
    if status == "success":
        ctx, row = load(project_id)
        ctx["status"] = "Active"
        for k in ("contacts", "resources", "tasks"):
            for it in ctx[k]:
                it["committed"] = True
        C.recompute(ctx, refs)
        saved = save(project_id, ctx, row["revision"], actor, f"Committed to JOSS ({pkg['submission_id']})")
        db.run("UPDATE projects SET committed_revision=?, status='Active' WHERE project_id=?", (saved["revision"], project_id))
        result["new_revision"] = saved["revision"]
    return result


def set_status(project_id, status, actor):
    if status not in ("On Hold", "Closed", "Active"):
        raise ApiError(422, "Status can only be set to On Hold, Closed or Active")
    ctx, row = load(project_id)
    if row["committed_revision"] is None:
        raise ApiError(409, "Only committed projects can be put On Hold / Closed / re-activated.")
    refs = masters.load_refs(project_id)
    ctx["status"] = status
    C.recompute(ctx, refs)
    audit(actor, project_id, "status.changed", "submit", {"status": status})
    saved = save(project_id, ctx, None, actor, f"Status → {status}")
    db.run("UPDATE joss_project SET process_status=? WHERE project_id=?", (status, project_id))
    return saved


def set_delegates(project_id, delegates, actor):
    ctx, row = load(project_id)
    d = [x.strip().lower() for x in delegates if x.strip()]
    db.run("UPDATE projects SET delegates=? WHERE project_id=?", (jd(d), project_id))
    audit(actor, project_id, "delegates.changed", "submit", {"delegates": d})
    return d


def simulate_logged_hours(project_id, task_id, hours, actor):
    """Demo helper (stands in for timesheets): marks a committed task as having logged hours."""
    t = db.one("SELECT * FROM joss_task WHERE project_id=? AND local_id=?", (project_id, task_id))
    if not t:
        raise ApiError(404, "Task is not committed to JOSS yet")
    db.run("UPDATE joss_task SET logged_hours=? WHERE project_id=? AND local_id=?", (hours, project_id, task_id))
    ctx, _ = load(project_id)
    for x in ctx["tasks"]:
        if x["id"] == task_id:
            x["has_logged_hours"] = hours > 0
    save(project_id, ctx, None, actor, f"Timesheet hours logged on {task_id} (simulated)")
    audit(actor, project_id, "timesheet.simulated", "tasks", {"task_id": task_id, "hours": hours})
    return {"task_id": task_id, "logged_hours": hours}


# ------------------------------------------------------------------ listings
def list_projects():
    out = []
    for r in db.rows("SELECT * FROM projects ORDER BY project_id DESC"):
        ctx = jl(r["context"])
        refs = None
        mods = rules.module_status(ctx, ctx.get("open_rules") or [])
        last = db.one("SELECT ts, saved_by FROM context_revisions WHERE project_id=? ORDER BY revision DESC LIMIT 1", (r["project_id"],))
        out.append({"project_id": r["project_id"], "opportunity_id": r["opportunity_id"], "name": C.val(ctx, "project_name") or ctx["sf"]["name"],
                    "customer": C.val(ctx, "customer_name") or ctx["sf"]["account_name"], "status": ctx["status"], "revision": r["revision"],
                    "committed_revision": r["committed_revision"], "start_date": C.val(ctx, "start_date"), "finish_date": C.val(ctx, "finish_date"),
                    "execution_model": C.val(ctx, "execution_model"), "modules_saved": sum(1 for m in C.MODULES if ctx["saved"].get(m)),
                    "blocks": sum(1 for h in ctx.get("open_rules", []) if h["level"] == "BLOCK"), "warns": sum(1 for h in ctx.get("open_rules", []) if h["level"] == "WARN"),
                    "updated_at": last["ts"] if last else r["created_at"], "updated_by": last["saved_by"] if last else None, "owner_email": r["owner_email"]})
    return out


def dashboard():
    projects = list_projects()
    by_status = {}
    for p in projects:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
    states = {"high": 0, "default": 0, "system": 0, "review": 0, "missing": 0, "confirmed": 0, "conflict": 0}
    qa_total = qa_accepted = 0
    for r in db.rows("SELECT context FROM projects"):
        ctx = jl(r["context"])
        for c in ctx["edit_project"].values():
            states[c["state"] or "missing"] = states.get(c["state"] or "missing", 0) + 1
        if ctx["qa"].get("combination_id"):
            qa_total += 1
            qa_accepted += 0 if ctx["qa"].get("overridden") else 1
    fields_total = sum(states.values()) or 1
    auto = states["high"] + states["default"] + states["system"] + states["review"]
    return {"projects": len(projects), "by_status": by_status, "field_states": states,
            "autofill_pct": round(100 * auto / fields_total, 1), "qa_total": qa_total, "qa_accepted": qa_accepted,
            "qa_acceptance_pct": round(100 * qa_accepted / qa_total, 1) if qa_total else None,
            "open_blocks": sum(p["blocks"] for p in projects if p["status"] not in ("Active", "Closed")),
            "recent_audit": audit_list(None, 8), "committed": sum(1 for p in projects if p["committed_revision"] is not None)}


def audit_list(project_id, limit=200):
    if project_id:
        rs = db.rows("SELECT * FROM audit_log WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))
    else:
        rs = db.rows("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    return [{**r, "detail": jl(r["detail"])} for r in rs]
