"""Writer for the JOSS database (decision D1 still open: API / stored procedures / staged import).
Today it writes to the simulated joss_* tables in SQLite with idempotent upserts keyed on (project_id, local id), so a retry
after a partial failure never creates duplicates.  Replace this class with an API-backed one when the write method is confirmed."""
from __future__ import annotations
from . import db
from . import clock
from . import context as C


class WriteError(Exception):
    pass


class SimulatedJossWriter:
    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at

    def _maybe_fail(self, module):
        if self.fail_at == module:
            raise WriteError(f"Simulated JOSS write failure while writing '{module}'.")

    def project(self, ctx: dict) -> dict:
        self._maybe_fail("project")
        v = lambda k: C.val(ctx, k)
        with db.conn() as c:
            c.execute("""INSERT INTO joss_project(project_id,opportunity_id,customer_name,project_name,description,start_date,finish_date,
                execution_model,sales_margin,margin_target,tolerance_pct,timesheet_approval,auto_timesheet_submit,customer_project_id,
                timesheet_approver_id,process_status,active_yn,sow_url,revision,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id) DO UPDATE SET customer_name=excluded.customer_name,project_name=excluded.project_name,
                description=excluded.description,start_date=excluded.start_date,finish_date=excluded.finish_date,execution_model=excluded.execution_model,
                sales_margin=excluded.sales_margin,margin_target=excluded.margin_target,tolerance_pct=excluded.tolerance_pct,
                timesheet_approval=excluded.timesheet_approval,auto_timesheet_submit=excluded.auto_timesheet_submit,
                customer_project_id=excluded.customer_project_id,timesheet_approver_id=excluded.timesheet_approver_id,
                process_status=excluded.process_status,active_yn=excluded.active_yn,sow_url=excluded.sow_url,revision=excluded.revision,updated_at=excluded.updated_at""",
                      (ctx["project_id"], ctx["opportunity_id"], v("customer_name"), v("project_name"), v("project_description"), v("start_date"),
                       v("finish_date"), v("execution_model"), v("sales_margin"), v("margin_target"), v("tolerance_pct"), v("timesheet_approval"),
                       v("auto_timesheet_submit"), v("customer_project_id"), ctx.get("timesheet_approver_id"), "In Setup", "N",
                       ctx.get("sow_url"), ctx["revision"], clock.now()))
        return {"status": "written", "joss_id": ctx["project_id"]}

    def finalize(self, ctx: dict) -> None:
        """Last step: the project becomes Active only when every module has been written."""
        today = clock.today().isoformat()
        s, f = C.project_dates(ctx)
        with db.conn() as c:
            c.execute("UPDATE joss_project SET process_status='Active', active_yn=?, updated_at=? WHERE project_id=?",
                      ("Y" if (s and f and s <= today <= f) else "N", clock.now(), ctx["project_id"]))

    def qa(self, ctx: dict) -> dict:
        self._maybe_fail("qa")
        q = ctx["qa"]
        with db.conn() as c:
            c.execute("""INSERT INTO joss_qa_profile(project_id,combination_id,match_score,overridden_yn,reason) VALUES(?,?,?,?,?)
                ON CONFLICT(project_id) DO UPDATE SET combination_id=excluded.combination_id,match_score=excluded.match_score,
                overridden_yn=excluded.overridden_yn,reason=excluded.reason""",
                      (ctx["project_id"], q["combination_id"], q.get("score"), "Y" if q.get("overridden") else "N", q.get("reason")))
        return {"status": "written", "records": 1}

    def contacts(self, ctx: dict) -> dict:
        self._maybe_fail("contacts")
        with db.conn() as c:
            for x in ctx["contacts"]:
                c.execute("""INSERT INTO joss_contact(project_id,local_id,role,associate_id,start_date,end_date,source) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(project_id,local_id) DO UPDATE SET role=excluded.role,associate_id=excluded.associate_id,
                    start_date=excluded.start_date,end_date=excluded.end_date,source=excluded.source""",
                          (ctx["project_id"], x["id"], x["role"], x["associate_id"], x["start"], x.get("end"), x.get("source")))
        return {"status": "written", "records": len(ctx["contacts"])}

    def resources(self, ctx: dict) -> dict:
        self._maybe_fail("resources")
        with db.conn() as c:
            for l in ctx["resources"]:
                c.execute("""INSERT INTO joss_resource(project_id,local_id,role,level,tier,location,technology,qty,bill_rate,cost_rate,hours,budget_amount,
                    associate_id,start_date,end_date,allocation_pct) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(project_id,local_id) DO UPDATE SET role=excluded.role,level=excluded.level,tier=excluded.tier,location=excluded.location,
                    technology=excluded.technology,qty=excluded.qty,bill_rate=excluded.bill_rate,cost_rate=excluded.cost_rate,hours=excluded.hours,
                    budget_amount=excluded.budget_amount,associate_id=excluded.associate_id,start_date=excluded.start_date,end_date=excluded.end_date,
                    allocation_pct=excluded.allocation_pct""",
                          (ctx["project_id"], l["id"], l["role"], l["level"], l.get("tier"), l["location"], l.get("technology"), l["qty"], l["bill_rate"],
                           l["cost_rate"], l["hours"], C.line_budget(l), l["associate_id"], l.get("start"), l.get("end"), l.get("allocation_pct")))
        return {"status": "written", "records": len(ctx["resources"])}

    def tasks(self, ctx: dict) -> dict:
        self._maybe_fail("tasks")
        with db.conn() as c:
            for t in ctx["tasks"]:
                c.execute("""INSERT INTO joss_task(project_id,local_id,task_name,assignee_id,billable_yn,active_yn,utilization_pct,start_date,end_date)
                    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,local_id) DO UPDATE SET task_name=excluded.task_name,assignee_id=excluded.assignee_id,
                    billable_yn=excluded.billable_yn,active_yn=excluded.active_yn,utilization_pct=excluded.utilization_pct,
                    start_date=excluded.start_date,end_date=excluded.end_date""",
                          (ctx["project_id"], t["id"], t["name"], t["assignee_id"], "Y" if t["billable"] else "N", "Y" if t["active"] else "N",
                           t["utilization"], t["start"], t["end"]))
        return {"status": "written", "records": len(ctx["tasks"])}
