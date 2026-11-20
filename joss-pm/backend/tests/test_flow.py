"""End-to-end tests of the PM Workspace API, mirroring the design's UAT scenarios (T-01 .. T-10).
Run:  cd backend && python -m unittest discover -s tests -v"""
import os
import tempfile
import unittest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["JOSS_DB"] = _tmp.name
os.environ["JOSS_TODAY"] = "2026-10-16"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

H = {"X-User-Email": "jaipal.banoth@jadeglobal.com"}
ACME, GLOBEX, INITECH, KESTREL, UMBRELLA = ("006AC00000A100%d" % i for i in range(1, 6))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cm = TestClient(app)
        cls.c = cls.cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)

    def setUp(self):
        # fresh, re-seeded database for every test (production duplicate-opportunity check is untouched)
        from app import seed
        path = os.environ["JOSS_DB"]
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass
        seed.seed()

    def create(self, opp):
        r = self.c.post("/api/projects", json={"opportunity_id": opp}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["context"]["project_id"]

    def view(self, pid):
        return self.c.get(f"/api/projects/{pid}").json()

    def chat(self, pid, module, msg, pending=None, structured=None):
        r = self.c.post(f"/api/projects/{pid}/chat/{module}", json={"message": msg, "pending": pending, "structured": structured}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def apply(self, pid, module, changes, expect=200):
        rev = self.view(pid)["context"]["revision"]
        r = self.c.post(f"/api/projects/{pid}/apply/{module}", json={"changes": changes, "expected_revision": rev}, headers=H)
        self.assertEqual(r.status_code, expect, r.text)
        return r

    def say_apply(self, pid, module, msg, pending=None):
        j = self.chat(pid, module, msg, pending)
        self.assertEqual(j["status"], "ready", j["reply"])
        self.apply(pid, module, j["changes"])
        return j

    def full_setup(self, opp=ACME):
        """Create + save every module so the project is ready to submit."""
        pid = self.create(opp)
        r = self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H).json()
        self.assertEqual(r["blocks"], [], r["blocks"])
        qa = self.view(pid)["context"]["qa"]["combination_id"]
        self.c.put(f"/api/projects/{pid}/qa", json={"combination_id": qa}, headers=H)
        self.say_apply(pid, "contacts", "Make Anita Rao the Project Manager from 1 Nov" if opp == ACME else "Make Anita Rao the Project Manager from 15 Nov")
        names = ["Anita Rao", "Priya Nair", "Rahul Patil", "Rohan Gupta", "Divya Menon", "Sanjay Bhatt"]
        for i in range(len(self.view(pid)["context"]["resources"])):
            self.say_apply(pid, "resources", f"assign {names[i]} to line {i + 1}")
        # lines of qty > 1 split off: assign every remaining unassigned line
        spare = ["Sneha Kulkarni", "Neha Joshi", "Arjun Iyer", "Meera Pillai", "Karan Mehta", "Rahul Sharma"]
        guard = 0
        while guard < 10:
            ctx = self.view(pid)["context"]
            idx = next((i for i, l in enumerate(ctx["resources"]) if not l["associate_id"]), None)
            if idx is None:
                break
            j = self.chat(pid, "resources", f"assign {spare.pop(0)} to line {idx + 1}")
            self.apply(pid, "resources", j["changes"])
            guard += 1
        self.c.post(f"/api/projects/{pid}/modules/tasks/save", json={}, headers=H)
        for m in ("contacts", "resources"):
            self.c.post(f"/api/projects/{pid}/modules/{m}/save", json={}, headers=H)
        return pid


class TestA1A2(Base):
    def test_t01_sow_prefill_and_qa(self):
        pid = self.create(ACME)
        ctx = self.view(pid)["context"]
        ep = ctx["edit_project"]
        self.assertEqual(ep["customer_name"]["value"], "Acme Corp Ltd")
        self.assertEqual(ep["start_date"]["value"], "2026-11-01")
        self.assertEqual(ep["finish_date"]["value"], "2027-03-31")
        self.assertEqual(ep["execution_model"]["value"], "Fixed Price")
        self.assertEqual(ep["customer_project_id"]["value"], "PO-88231")
        self.assertEqual(ep["tolerance_pct"]["value"], 5.0)
        self.assertEqual(ep["margin_target"]["value"], 30)
        self.assertEqual(ctx["status"], "Draft")
        self.assertEqual(ctx["qa"]["suggestions"][0]["score"], 1.0)
        self.assertEqual(ctx["qa"]["combination_id"], ctx["qa"]["suggestions"][0]["combination_id"])
        self.assertIn("ERP Cloud", ctx["qa"]["suggestions"][0]["label"])

    def test_t02_missing_po_and_t03_conflict(self):
        pid = self.create(GLOBEX)
        ctx = self.view(pid)["context"]
        ep = ctx["edit_project"]
        self.assertIsNone(ep["customer_project_id"]["value"])                  # T-02: blank, not guessed
        self.assertEqual(ep["start_date"]["state"], "conflict")                # T-03: SOW Dec 1 vs Salesforce Nov 15
        self.assertEqual(ep["start_date"]["conflict"]["salesforce_value"], "2026-11-15")
        save = self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H).json()
        self.assertTrue(any(b["id"] == "X-06" for b in save["blocks"]))
        fixed = self.c.put(f"/api/projects/{pid}/edit-project", json={"resolve": {"start_date": "sow"}, "save": True}, headers=H).json()
        self.assertEqual(fixed["context"]["edit_project"]["start_date"]["value"], "2026-12-01")
        self.assertFalse(any(b["id"] == "X-06" for b in fixed["blocks"]))

    def test_no_sow_form_is_manual(self):
        pid = self.create(UMBRELLA)
        ctx = self.view(pid)["context"]
        self.assertTrue(ctx["a1"]["errors"])
        r = self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {"customer_name": "Umbrella Retail Inc", "project_name": "Umbrella CRM Upgrade",
                                                                             "start_date": "2027-01-11", "finish_date": "2027-04-30", "execution_model": "T&M"}, "save": True}, headers=H).json()
        self.assertEqual(r["blocks"], [])
        self.assertEqual(r["context"]["status"], "In Setup")

    def test_ep_rules(self):
        pid = self.create(KESTREL)
        r = self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {"finish_date": "2026-11-01", "tolerance_pct": 140, "execution_model": "Barter"}, "save": True}, headers=H).json()
        ids = {b["id"] for b in r["blocks"]}
        self.assertTrue({"EP-01", "EP-04", "EP-05"} <= ids, ids)

    def test_qa_override_requires_reason(self):
        pid = self.create(ACME)
        bad = self.c.put(f"/api/projects/{pid}/qa", json={"combination_id": "QA-105"}, headers=H)
        alt = self.view(pid)["context"]["qa"]["suggestions"][1]["combination_id"]
        self.assertEqual(self.c.put(f"/api/projects/{pid}/qa", json={"combination_id": alt}, headers=H).status_code, 422)
        ok = self.c.put(f"/api/projects/{pid}/qa", json={"combination_id": alt, "reason": "Customer asked for waterfall"}, headers=H)
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["context"]["qa"]["overridden"])
        self.assertEqual(self.c.put(f"/api/projects/{pid}/qa", json={"combination_id": "QA-999"}, headers=H).status_code, 422)
        self.assertEqual(len(self.c.get(f"/api/projects/{pid}/qa-overrides").json()), 1)


class TestChatAgents(Base):
    def test_t04_task_flow_with_followup(self):
        pid = self.create(ACME)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H)
        self.say_apply(pid, "resources", "assign Rahul Patil to line 3")
        j1 = self.chat(pid, "tasks", "Create a Data Migration task for Rahul, 50% from 1 Nov.")
        self.assertEqual(j1["status"], "needs_info")
        self.assertEqual(j1["missing"], ["end"])
        j2 = self.chat(pid, "tasks", "15 Dec", j1["pending"])
        self.assertEqual(j2["status"], "ready", j2["reply"])
        t = j2["changes"][0]["task"]
        self.assertEqual((t["name"], t["utilization"], t["start"], t["end"], t["billable"]), ("Data Migration", 50.0, "2026-11-01", "2026-12-15", True))
        self.apply(pid, "tasks", j2["changes"])
        self.assertEqual(len(self.view(pid)["context"]["tasks"]), 1)
        # T-01 update + duplicate name rejected
        up = self.say_apply(pid, "tasks", "Extend Data Migration to 30 Dec")
        self.assertEqual(self.view(pid)["context"]["tasks"][0]["end"], "2026-12-30")
        dup = self.chat(pid, "tasks", "Create a Data Migration task for Rahul, 10% from 1 Nov to 2 Nov")
        self.assertEqual(dup["status"], "blocked")
        self.assertTrue(any(h["id"] == "TK-01" for h in dup["rule_hits"]))

    def test_t05_assignee_not_in_pool_and_date_rules(self):
        pid = self.create(ACME)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H)
        self.say_apply(pid, "resources", "assign Rahul Patil to line 3")
        j = self.chat(pid, "tasks", "Create a UAT task for Sneha, 50% from 1 Nov to 10 Nov")
        self.assertEqual(j["status"], "blocked")
        self.assertTrue(any(h["id"] == "TK-02" for h in j["rule_hits"]))
        self.assertIn("Valid assignees", j["reply"])
        j = self.chat(pid, "tasks", "Create a Cutover task for Rahul 50% from 1 Nov to 30 Apr")
        self.assertTrue(any(h["id"] == "TK-03" for h in j["rule_hits"]))
        j = self.chat(pid, "tasks", "Create a Prep task for Rahul 150% from 1 Nov to 10 Nov")
        self.assertTrue(any(h["id"] == "TK-04" for h in j["rule_hits"]))
        self.assertEqual(self.apply(pid, "tasks", [{"op": "add", "task": {"name": "X", "assignee_id": "E2215", "utilization": 50, "start": "2026-11-01",
                                                                            "end": "2026-11-05", "billable": True, "active": True}}], expect=422).status_code, 422)

    def test_tk04_warn_overallocation(self):
        pid = self.create(ACME)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H)
        self.say_apply(pid, "resources", "assign Rahul Patil to line 3")
        self.say_apply(pid, "tasks", "Create Design for Rahul 60% from 1 Nov to 30 Nov")
        j = self.chat(pid, "tasks", "Create Build for Rahul 60% from 1 Nov to 30 Nov")
        self.assertEqual(j["status"], "ready")
        self.assertTrue(any(h["id"] == "TK-04" and h["level"] == "WARN" for h in j["rule_hits"]))
        self.assertIn("120%", j["reply"])

    def test_non_billable_model_forces_no(self):
        pid = self.create(UMBRELLA)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {"customer_name": "Umbrella Retail Inc", "project_name": "U", "start_date": "2027-01-11",
                                                                         "finish_date": "2027-04-30", "execution_model": "Internal"}, "save": True}, headers=H)
        self.say_apply(pid, "resources", "assign Rahul Patil to line 2")
        j = self.chat(pid, "tasks", "Create Build for Rahul 50% from 15 Jan to 20 Jan")
        self.assertFalse(j["changes"][0]["task"]["billable"])
        bad = self.chat(pid, "tasks", "Create Test for Rahul 50% from 15 Jan to 20 Jan, billable")
        self.assertTrue(any(h["id"] == "TK-05" for h in bad["rule_hits"]))

    def test_t06_t07_contact_handover(self):
        pid = self.create(ACME)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H)
        self.say_apply(pid, "contacts", "Amit as Tech Lead from 1 Nov")
        j = self.say_apply(pid, "contacts", "Make Priya the Tech Lead from 1 Jan")
        self.assertEqual([r["action"] for r in j["preview"]["rows"]], ["CLOSE", "CREATE"])
        cs = {c["associate_id"]: c for c in self.view(pid)["context"]["contacts"]}
        self.assertEqual(cs["E2301"]["end"], "2026-12-31")                      # JC-03: new start - 1 day
        self.assertEqual(cs["E2215"]["start"], "2027-01-01")
        # PM becomes the timesheet approver (X-03)
        self.say_apply(pid, "contacts", "Anita Rao as Project Manager from 1 Nov")
        self.assertEqual(self.view(pid)["context"]["timesheet_approver_id"], "E1043")

    def test_contact_rules(self):
        pid = self.create(ACME)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H)
        amb = self.chat(pid, "contacts", "Make Rahul the Functional Consultant from 1 Nov")
        self.assertEqual(amb["status"], "needs_info")                           # Rahul Patil vs Rahul Sharma
        ok = self.chat(pid, "contacts", "1", amb["pending"])
        self.assertEqual(ok["status"], "ready", ok["reply"])
        inactive = self.chat(pid, "contacts", "Suresh Kumar as QA Lead from 1 Nov")
        self.assertEqual(inactive["status"], "blocked")
        self.assertTrue(any(h["id"] == "JC-04" for h in inactive["rule_hits"]))
        early = self.chat(pid, "contacts", "Amit as Tech Lead from 1 Oct")
        self.assertTrue(any(h["id"] == "JC-02" for h in early["rule_hits"]))
        self.say_apply(pid, "contacts", "Amit as Tech Lead from 1 Nov")
        clash = self.chat(pid, "contacts", "Make Priya the Tech Lead from 1 Nov")
        self.assertEqual(clash["status"], "blocked")                            # previous holder would end before start

    def test_t08_resources(self):
        pid = self.create(ACME)
        self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {}, "save": True}, headers=H)
        before = len(self.view(pid)["context"]["resources"])
        j = self.chat(pid, "resources", "add 1 TE4 offshore QA")                 # RM-02: no associate, refuse
        self.assertEqual(j["status"], "needs_info")
        self.assertTrue(any(h["id"] == "RM-02" for h in j["rule_hits"]))
        self.assertEqual(len(self.view(pid)["context"]["resources"]), before)
        j = self.chat(pid, "resources", "Divya", j["pending"])
        self.assertEqual(j["status"], "ready", j["reply"])
        self.apply(pid, "resources", j["changes"])
        ctx = self.view(pid)["context"]
        self.assertEqual(len(ctx["resources"]), before + 1)
        new = ctx["resources"][-1]
        self.assertEqual((new["bill_rate"], new["cost_rate"], new["associate_id"]), (48, 26, "E2350"))
        self.assertEqual(new["budget"], new["bill_rate"] * new["hours"])         # RM-04: qty x rate x hours
        # split + rate card
        j = self.chat(pid, "resources", "move 1 of the 3 TE3s to onshore")
        self.assertEqual(j["status"], "ready", j["reply"])
        self.apply(pid, "resources", j["changes"])
        loc = [(l["qty"], l["location"], l["bill_rate"]) for l in self.view(pid)["context"]["resources"] if l["level"] == "TE3" and l["role"] == "Functional Consultant"]
        self.assertIn((1, "onshore", 80), loc)
        # release
        j = self.say_apply(pid, "resources", "release line 1 on 31 Dec")
        self.assertTrue(self.view(pid)["context"]["resources"][0]["released"])
        # assigning a qty>1 line splits one unit off (RM-06 keeps one associate per line)
        qtys = [l["qty"] for l in self.view(pid)["context"]["resources"]]
        self.assertTrue(all(q >= 1 for q in qtys))
        # RM-03 warn: Karan has 60% elsewhere
        j = self.chat(pid, "resources", "assign Karan Mehta to line 4")
        self.assertTrue(any(h["id"] == "RM-03" for h in j["rule_hits"]))


class TestSubmit(Base):
    def test_t09_t10_commit_idempotent_and_retry(self):
        pid = self.full_setup()
        v = self.view(pid)
        self.assertEqual(v["context"]["status"], "Ready to Submit", v["submit_hits"])
        # X-04: a non-PM cannot submit
        r = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-x"}, headers={"X-User-Email": "karan.mehta@jadeglobal.com"}).json()
        self.assertEqual(r["result"]["errors"][0]["rule"], "X-04")
        # T-10: a failure while writing resources -> stop, report, keep earlier modules
        rev = v["context"]["revision"]
        bad = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-1", "expected_revision": rev, "fail_at": "resources"}, headers=H).json()["result"]
        self.assertEqual(bad["overall_status"], "failed")
        self.assertEqual([bad["modules"][m]["status"] for m in ("project", "qa", "contacts", "resources", "tasks")], ["written", "written", "written", "failed", "skipped"])
        self.assertEqual(self.view(pid)["context"]["status"], "Ready to Submit")
        # retry with the same submission id: no duplicates
        ok = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-1", "expected_revision": rev}, headers=H).json()["result"]
        self.assertEqual(ok["overall_status"], "success", ok)
        j = self.c.get(f"/api/projects/{pid}/joss").json()
        self.assertEqual(j["project"]["process_status"], "Active")
        self.assertEqual(len(j["contacts"]), len(self.view(pid)["context"]["contacts"]))
        n_res = len(j["resources"])
        # replaying the successful submission is a no-op
        again = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-1", "expected_revision": rev}, headers=H).json()["result"]
        self.assertTrue(again.get("idempotent_replay"))
        self.assertEqual(len(self.c.get(f"/api/projects/{pid}/joss").json()["resources"]), n_res)
        # status + approver
        after = self.view(pid)
        self.assertEqual(after["context"]["status"], "Active")
        self.assertEqual(j["project"]["timesheet_approver_id"], "E1043")
        # editing after commit -> new revision, still Active, flagged as pending changes
        self.say_apply(pid, "contacts", "Make Vikram Desai the Delivery Manager from 1 Nov")
        self.assertTrue(self.view(pid)["pending_changes"])
        # stale revision rejected (X-01)
        stale = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-2", "expected_revision": rev}, headers=H).json()["result"]
        self.assertEqual(stale["errors"][0]["rule"], "X-01")

    def test_submit_blocked_when_modules_missing(self):
        pid = self.create(ACME)
        r = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-b"}, headers=H).json()["result"]
        self.assertEqual(r["overall_status"], "failed")
        rules = {e["rule"] for e in r["errors"]}
        self.assertTrue({"X-02", "JC-05", "RM-01"} <= rules, rules)
        self.assertTrue(all(m["status"] == "skipped" for m in r["modules"].values()))
        self.assertIsNone(self.c.get(f"/api/projects/{pid}/joss").json()["project"])

    def test_tk06_logged_hours(self):
        pid = self.full_setup()
        self.say_apply(pid, "tasks", "Create Design for Rahul 40% from 1 Nov to 30 Nov")
        self.c.post(f"/api/projects/{pid}/modules/tasks/save", json={}, headers=H)
        res = self.c.post(f"/api/projects/{pid}/submit", json={"submission_id": "sub-t"}, headers=H).json()["result"]
        self.assertEqual(res["overall_status"], "success", res)
        tid = self.view(pid)["context"]["tasks"][0]["id"]
        self.c.post(f"/api/projects/{pid}/tasks/{tid}/simulate-hours", json={"hours": 16}, headers=H)
        self.apply(pid, "tasks", [{"op": "remove", "task_id": tid}], expect=422)           # delete refused
        self.say_apply(pid, "tasks", "Deactivate Design")                                    # deactivate allowed
        self.assertFalse(self.view(pid)["context"]["tasks"][0]["active"])

    def test_revisions_and_audit(self):
        pid = self.create(ACME)
        revs = self.c.get(f"/api/projects/{pid}/revisions").json()
        self.assertGreaterEqual(len(revs), 1)
        self.assertEqual(self.c.get(f"/api/projects/{pid}/revisions/{revs[-1]['revision']}").status_code, 200)
        actions = {a["action"] for a in self.c.get(f"/api/audit?project_id={pid}").json()}
        self.assertTrue({"project.created", "a1.extracted"} <= actions)
        stale = self.c.put(f"/api/projects/{pid}/edit-project", json={"fields": {"project_name": "Z"}, "expected_revision": 999}, headers=H)
        self.assertEqual(stale.status_code, 409)


if __name__ == "__main__":
    unittest.main()
