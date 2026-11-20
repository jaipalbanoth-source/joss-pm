"""SQLite persistence (stdlib only). One file holds the PM workspace data AND the simulated JOSS database
(tables prefixed joss_). Swap `joss_writer.py` for a real API / SP writer once decision D1 is made."""
from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "joss.db")


def db_path() -> str:
    return os.environ.get("JOSS_DB", DEFAULT_PATH)


@contextmanager
def conn():
    c = sqlite3.connect(db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def rows(sql: str, args=()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql: str, args=()) -> dict | None:
    r = rows(sql, args)
    return r[0] if r else None


def run(sql: str, args=()) -> int:
    with conn() as c:
        return c.execute(sql, args).lastrowid


def jl(s):
    return json.loads(s) if s else None


def jd(o) -> str:
    return json.dumps(o, ensure_ascii=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS associates(associate_id TEXT PRIMARY KEY, name TEXT, email TEXT, status TEXT,
  location TEXT, title TEXT, other_allocation_pct INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS customers(customer_id TEXT PRIMARY KEY, name TEXT UNIQUE, sf_account TEXT);
CREATE TABLE IF NOT EXISTS masters(kind TEXT, code TEXT, label TEXT, meta TEXT, PRIMARY KEY(kind, code));
CREATE TABLE IF NOT EXISTS qa_master(combination_id TEXT PRIMARY KEY, platform TEXT, type TEXT, delivery TEXT,
  commercial TEXT, label TEXT);
CREATE TABLE IF NOT EXISTS sf_opportunities(opportunity_id TEXT PRIMARY KEY, name TEXT, account_name TEXT,
  start_date TEXT, end_date TEXT, sow_id TEXT, resource_lines TEXT, stage TEXT);
CREATE TABLE IF NOT EXISTS sows(sow_id TEXT PRIMARY KEY, filename TEXT, text TEXT, source TEXT, uploaded_at TEXT);
CREATE TABLE IF NOT EXISTS projects(project_id TEXT PRIMARY KEY, opportunity_id TEXT, owner_email TEXT,
  delegates TEXT DEFAULT '[]', created_at TEXT, revision INTEGER DEFAULT 0, committed_revision INTEGER,
  status TEXT, context TEXT);
CREATE TABLE IF NOT EXISTS context_revisions(project_id TEXT, revision INTEGER, context TEXT, saved_by TEXT,
  ts TEXT, note TEXT, PRIMARY KEY(project_id, revision));
CREATE TABLE IF NOT EXISTS chat_log(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, module TEXT,
  role TEXT, content TEXT, payload TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS qa_overrides(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, suggested TEXT,
  chosen TEXT, reason TEXT, ts TEXT, actor TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, project_id TEXT,
  action TEXT, module TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS submissions(submission_id TEXT PRIMARY KEY, project_id TEXT, revision INTEGER,
  status TEXT, result TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS joss_project(project_id TEXT PRIMARY KEY, opportunity_id TEXT, customer_name TEXT,
  project_name TEXT, description TEXT, start_date TEXT, finish_date TEXT, execution_model TEXT,
  sales_margin REAL, margin_target REAL, tolerance_pct REAL, timesheet_approval TEXT,
  auto_timesheet_submit TEXT, customer_project_id TEXT, timesheet_approver_id TEXT, process_status TEXT,
  active_yn TEXT, sow_url TEXT, revision INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS joss_qa_profile(qa_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT UNIQUE,
  combination_id TEXT, match_score REAL, overridden_yn TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS joss_contact(contact_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
  local_id TEXT, role TEXT, associate_id TEXT, start_date TEXT, end_date TEXT, source TEXT,
  UNIQUE(project_id, local_id));
CREATE TABLE IF NOT EXISTS joss_resource(line_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
  local_id TEXT, role TEXT, level TEXT, tier TEXT, location TEXT, technology TEXT, qty REAL, bill_rate REAL,
  cost_rate REAL, hours REAL, budget_amount REAL, associate_id TEXT, start_date TEXT, end_date TEXT,
  allocation_pct REAL, UNIQUE(project_id, local_id));
CREATE TABLE IF NOT EXISTS joss_task(task_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, local_id TEXT,
  task_name TEXT, assignee_id TEXT, billable_yn TEXT, active_yn TEXT, utilization_pct REAL, start_date TEXT,
  end_date TEXT, logged_hours REAL DEFAULT 0, UNIQUE(project_id, local_id));
"""


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
