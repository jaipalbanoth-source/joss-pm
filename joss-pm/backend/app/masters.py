"""Read access to masters / directory / mock Salesforce (the agents' read-only data sources)."""
from __future__ import annotations
from . import db
from .db import jl


def exec_models() -> dict:
    return {r["code"]: jl(r["meta"]) for r in db.rows("SELECT * FROM masters WHERE kind='execution_model' ORDER BY rowid")}


def roles() -> dict:
    return {r["code"]: jl(r["meta"])["single_holder"] for r in db.rows("SELECT * FROM masters WHERE kind='contact_role' ORDER BY rowid")}


def process_statuses() -> list:
    return [r["code"] for r in db.rows("SELECT code FROM masters WHERE kind='process_status' ORDER BY rowid")]


def rate_card() -> dict:
    return {r["code"]: jl(r["meta"]) for r in db.rows("SELECT * FROM masters WHERE kind='rate_card'")}


def directory() -> dict:
    return {a["associate_id"]: a for a in db.rows("SELECT * FROM associates ORDER BY name")}


def customers() -> list:
    return [r["name"] for r in db.rows("SELECT name FROM customers ORDER BY name")]


def qa_master() -> list:
    return db.rows("SELECT * FROM qa_master ORDER BY combination_id")


def opportunity(opp_id: str) -> dict | None:
    o = db.one("SELECT * FROM sf_opportunities WHERE opportunity_id=?", (opp_id,))
    if o:
        o["resource_lines"] = jl(o["resource_lines"])
    return o


def opportunities() -> list:
    out = []
    for o in db.rows("SELECT * FROM sf_opportunities ORDER BY opportunity_id"):
        o["resource_lines"] = jl(o["resource_lines"])
        out.append(o)
    return out


def sow(sow_id: str | None) -> dict | None:
    return db.one("SELECT * FROM sows WHERE sow_id=?", (sow_id,)) if sow_id else None


def load_refs(project_id: str | None = None, ctx: dict | None = None) -> dict:
    d = directory()
    other_names = set()
    for p in db.rows("SELECT project_id, context FROM projects"):
        if p["project_id"] == project_id:
            continue
        c = jl(p["context"]) or {}
        ep = c.get("edit_project", {})
        cust = (ep.get("customer_name") or {}).get("value")
        name = (ep.get("project_name") or {}).get("value")
        if cust and name:
            other_names.add((cust.casefold(), name.casefold()))
    logged = {r["local_id"] for r in db.rows(
        "SELECT local_id FROM joss_task WHERE project_id=? AND logged_hours>0", (project_id,))} if project_id else set()
    return {"directory": d, "customers": customers(), "exec_models": exec_models(), "roles": roles(),
            "qa": {q["combination_id"]: q for q in qa_master()}, "other_names": other_names, "logged_tasks": logged,
            "rate_card": rate_card()}
