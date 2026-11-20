from __future__ import annotations
import io
import os
from typing import Any, Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import context as C, db, masters, rules, services as S
from ..db import jl

router = APIRouter(prefix="/api")
DEFAULT_USER = "jaipal.banoth@jadeglobal.com"


def actor(x_user_email: Optional[str]) -> str:
    return (x_user_email or DEFAULT_USER).strip().lower()


def guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except S.ApiError as e:
        raise HTTPException(e.status, detail={"message": e.message, "hits": e.hits, **e.extra})


# ------------------------------------------------------------------ reference data
@router.get("/health")
def health():
    return {"ok": True}


@router.get("/masters")
def get_masters():
    return {"customers": masters.customers(), "execution_models": masters.exec_models(), "contact_roles": masters.roles(),
            "process_statuses": masters.process_statuses(), "qa_master": masters.qa_master(), "rate_card": masters.rate_card(),
            "associates": list(masters.directory().values()), "edit_fields": [{"key": k, "label": l, "type": t, "mandatory": m} for k, l, t, m in C.EDIT_FIELDS],
            "modules": [{"key": m, "label": C.MODULE_LABELS[m]} for m in C.MODULES]}


@router.get("/rules")
def get_rules():
    return [{"id": r[0], "module": r[1], "level": r[2], "text": r[3]} for r in rules.RULES]


@router.get("/opportunities")
def get_opps():
    existing = {r["opportunity_id"]: r["project_id"] for r in db.rows("SELECT opportunity_id, project_id FROM projects")}
    out = []
    for o in masters.opportunities():
        sow = masters.sow(o["sow_id"])
        out.append({**o, "sow_filename": sow["filename"] if sow else None, "project_id": existing.get(o["opportunity_id"]),
                    "estimate_total": sum(C.line_budget({"qty": l["qty"], "bill_rate": l["bill_rate"], "hours": l["hours"]}) for l in o["resource_lines"])})
    return out


@router.get("/dashboard")
def dashboard():
    return S.dashboard()


@router.get("/audit")
def audit(project_id: Optional[str] = None, limit: int = 200):
    return S.audit_list(project_id, limit)


# ------------------------------------------------------------------ projects
class CreateProject(BaseModel):
    opportunity_id: str


@router.get("/projects")
def list_projects():
    return S.list_projects()


@router.post("/projects")
def create_project(body: CreateProject, x_user_email: Optional[str] = Header(None)):
    ctx = guard(S.create_project, body.opportunity_id, actor(x_user_email))
    return guard(S.get_view, ctx["project_id"])


@router.get("/projects/{pid}")
def get_project(pid: str):
    return guard(S.get_view, pid)


@router.delete("/projects/{pid}")
def delete_project(pid: str, x_user_email: Optional[str] = Header(None)):
    guard(S.delete_project, pid, actor(x_user_email))
    return {"deleted": pid}


@router.get("/projects/{pid}/sow")
def get_sow(pid: str):
    ctx, _ = guard(S.load, pid)
    sow = masters.sow(ctx.get("sow_id"))
    if not sow:
        raise HTTPException(404, detail={"message": "No SOW attached to this project"})
    return sow


class SowText(BaseModel):
    text: str
    filename: str = "pasted-sow.txt"
    keep_pm_edits: bool = True


def _read_upload(name: str, data: bytes) -> str:
    if name.lower().endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    if name.lower().endswith(".docx"):
        import re
        import zipfile
        xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf8", "ignore")
        return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
    return data.decode("utf8", "ignore")


@router.post("/projects/{pid}/sow")
def replace_sow(pid: str, body: SowText, x_user_email: Optional[str] = Header(None)):
    guard(S.load, pid)
    guard(S.rerun_sow, pid, actor(x_user_email), None, body.filename, body.text, body.keep_pm_edits)
    return guard(S.get_view, pid)


@router.post("/projects/{pid}/sow/upload")
async def upload_sow(pid: str, file: UploadFile = File(...), x_user_email: Optional[str] = Header(None)):
    guard(S.load, pid)
    data = await file.read()
    try:
        text = _read_upload(file.filename or "upload.txt", data)
    except Exception as e:  # unreadable PDF etc.
        raise HTTPException(422, detail={"message": f"Could not read the file: {e}"})
    guard(S.rerun_sow, pid, actor(x_user_email), None, file.filename, text, True)
    return guard(S.get_view, pid)


class Rerun(BaseModel):
    keep_pm_edits: bool = True


@router.post("/projects/{pid}/a1/run")
def rerun_a1(pid: str, body: Rerun = Rerun(), x_user_email: Optional[str] = Header(None)):
    guard(S.rerun_sow, pid, actor(x_user_email), None, None, None, body.keep_pm_edits)
    return guard(S.get_view, pid)


class EditBody(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    resolve: dict[str, str] = Field(default_factory=dict)
    save: bool = False
    expected_revision: Optional[int] = None


@router.put("/projects/{pid}/edit-project")
def edit_project(pid: str, body: EditBody, x_user_email: Optional[str] = Header(None)):
    r = guard(S.update_edit_project, pid, body.fields, body.resolve, body.save, body.expected_revision, actor(x_user_email))
    v = guard(S.get_view, pid)
    v["blocks"], v["a2_ran"] = r["blocks"], r["a2_ran"]
    return v


class QaBody(BaseModel):
    combination_id: str
    reason: Optional[str] = None
    expected_revision: Optional[int] = None


@router.put("/projects/{pid}/qa")
def set_qa(pid: str, body: QaBody, x_user_email: Optional[str] = Header(None)):
    guard(S.select_qa, pid, body.combination_id, body.reason, body.expected_revision, actor(x_user_email))
    return guard(S.get_view, pid)


class ModuleSave(BaseModel):
    expected_revision: Optional[int] = None


@router.post("/projects/{pid}/modules/{module}/save")
def save_module(pid: str, module: str, body: ModuleSave = ModuleSave(), x_user_email: Optional[str] = Header(None)):
    guard(S.save_module, pid, module, body.expected_revision, actor(x_user_email))
    return guard(S.get_view, pid)


# ------------------------------------------------------------------ chat agents
class ChatBody(BaseModel):
    message: str = ""
    pending: Optional[dict] = None
    structured: Optional[dict] = None


@router.post("/projects/{pid}/chat/{module}")
def chat(pid: str, module: str, body: ChatBody, x_user_email: Optional[str] = Header(None)):
    return guard(S.chat, pid, module, body.message, body.pending, body.structured, actor(x_user_email))


@router.get("/projects/{pid}/chat/{module}")
def chat_history(pid: str, module: str):
    guard(S.load, pid)
    return S.chat_history(pid, module)


class ApplyBody(BaseModel):
    changes: list[dict]
    expected_revision: Optional[int] = None


@router.post("/projects/{pid}/apply/{module}")
def apply(pid: str, module: str, body: ApplyBody, x_user_email: Optional[str] = Header(None)):
    guard(S.apply_changes, pid, module, body.changes, body.expected_revision, actor(x_user_email))
    return guard(S.get_view, pid)


# ------------------------------------------------------------------ submit / lifecycle
class SubmitBody(BaseModel):
    submission_id: Optional[str] = None
    expected_revision: Optional[int] = None
    fail_at: Optional[str] = None      # demo / UAT T-10: simulate a JOSS write failure at a module


@router.get("/projects/{pid}/package")
def package(pid: str, x_user_email: Optional[str] = Header(None)):
    pkg, _, _ = guard(S.build_package, pid, actor(x_user_email))
    pkg.pop("context", None)
    return pkg


@router.post("/projects/{pid}/submit")
def submit(pid: str, body: SubmitBody, x_user_email: Optional[str] = Header(None)):
    fail_at = body.fail_at if os.environ.get("JOSS_ALLOW_FAULT_INJECTION", "1") == "1" else None
    result = guard(S.submit, pid, body.submission_id, body.expected_revision, fail_at, actor(x_user_email))
    return {"result": result, "view": guard(S.get_view, pid)}


class StatusBody(BaseModel):
    status: str


@router.post("/projects/{pid}/status")
def set_status(pid: str, body: StatusBody, x_user_email: Optional[str] = Header(None)):
    guard(S.set_status, pid, body.status, actor(x_user_email))
    return guard(S.get_view, pid)


class DelegatesBody(BaseModel):
    delegates: list[str]


@router.put("/projects/{pid}/delegates")
def delegates(pid: str, body: DelegatesBody, x_user_email: Optional[str] = Header(None)):
    guard(S.set_delegates, pid, body.delegates, actor(x_user_email))
    return guard(S.get_view, pid)


class HoursBody(BaseModel):
    hours: float = 8


@router.post("/projects/{pid}/tasks/{tid}/simulate-hours")
def simulate_hours(pid: str, tid: str, body: HoursBody, x_user_email: Optional[str] = Header(None)):
    return guard(S.simulate_logged_hours, pid, tid, body.hours, actor(x_user_email))


@router.get("/projects/{pid}/revisions")
def revisions(pid: str):
    guard(S.load, pid)
    return db.rows("SELECT project_id, revision, saved_by, ts, note FROM context_revisions WHERE project_id=? ORDER BY revision DESC", (pid,))


@router.get("/projects/{pid}/revisions/{rev}")
def revision(pid: str, rev: int):
    r = db.one("SELECT * FROM context_revisions WHERE project_id=? AND revision=?", (pid, rev))
    if not r:
        raise HTTPException(404, detail={"message": "Revision not found"})
    return {**r, "context": jl(r["context"])}


@router.get("/projects/{pid}/qa-overrides")
def qa_overrides(pid: str):
    return db.rows("SELECT * FROM qa_overrides WHERE project_id=? ORDER BY id DESC", (pid,))


@router.get("/projects/{pid}/joss")
def joss_records(pid: str):
    """What the Commit agent has written to the (simulated) JOSS database."""
    return {"project": db.one("SELECT * FROM joss_project WHERE project_id=?", (pid,)),
            "qa": db.one("SELECT * FROM joss_qa_profile WHERE project_id=?", (pid,)),
            "contacts": db.rows("SELECT * FROM joss_contact WHERE project_id=?", (pid,)),
            "resources": db.rows("SELECT * FROM joss_resource WHERE project_id=?", (pid,)),
            "tasks": db.rows("SELECT * FROM joss_task WHERE project_id=?", (pid,)),
            "submissions": [{**s, "result": jl(s["result"])} for s in db.rows("SELECT * FROM submissions WHERE project_id=? ORDER BY ts DESC", (pid,))]}
