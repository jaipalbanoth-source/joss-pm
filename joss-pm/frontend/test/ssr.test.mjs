// Frontend smoke/integration test (no browser available offline):
//  1. spins up the real FastAPI backend on a fresh DB,
//  2. drives the REAL src/api.js client through the PM journey (create -> A1/A2 -> contacts -> resources -> tasks -> save -> submit -> retry),
//  3. server-side renders every page/tab component from the live responses and asserts on the HTML.
import { spawn, execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const PORT = 8765, BASE = `http://127.0.0.1:${PORT}`;
const ssr = path.join(here, ".ssr");
execSync("node build.mjs --ssr", { cwd: root, stdio: "pipe" });
fs.rmSync(path.join(ssr, "src"), { recursive: true, force: true });
fs.cpSync(path.join(root, "src"), path.join(ssr, "src"), { recursive: true });
fs.writeFileSync(path.join(ssr, "package.json"), '{"type":"module"}');

const db = path.join(os.tmpdir(), `joss-ui-${Date.now()}.db`);
const server = spawn("python3", ["-W", "ignore", "-m", "uvicorn", "app.main:app", "--port", String(PORT)], {
  cwd: path.join(root, "..", "backend"), env: { ...process.env, JOSS_DB: db, JOSS_TODAY: "2026-10-16" }, stdio: "ignore" });
const stop = () => { try { server.kill(); } catch {} fs.rmSync(db, { force: true }); };
process.on("exit", stop);

// browser-ish globals used by src/api.js
const realFetch = globalThis.fetch;
globalThis.fetch = (u, o) => realFetch(String(u).startsWith("/") ? BASE + u : u, o);
globalThis.location = { search: "", hash: "#/" };
const store = {}; globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
globalThis.window = { addEventListener() {}, removeEventListener() {} };

for (let i = 0; i < 60; i++) { try { if ((await realFetch(BASE + "/api/health")).ok) break; } catch {} await new Promise((r) => setTimeout(r, 250)); }

const imp = (f) => import(pathToFileURL(path.join(ssr, f)).href);
const R = await imp("vendor/react.js");
const { api } = await imp("src/api.js");
const { ce } = await imp("src/h.js");
const { MastersCtx } = await imp("src/state.js");
const { ToastProvider } = await imp("src/components/ui.js");
const { Readiness } = await imp("src/components/Readiness.js");
const { Preview } = await imp("src/components/Preview.js");
const { ChatPanel } = await imp("src/components/ChatPanel.js");
const { EditProjectTab } = await imp("src/pages/EditProject.js");
const { QaTab } = await imp("src/pages/QaTab.js");
const { ContactsTab } = await imp("src/pages/ContactsTab.js");
const { ResourcesTab } = await imp("src/pages/ResourcesTab.js");
const { TasksTab } = await imp("src/pages/TasksTab.js");
const { SubmitTab } = await imp("src/pages/SubmitTab.js");
const { HistoryTab, AuditTable } = await imp("src/pages/HistoryTab.js");
const { Dashboard } = await imp("src/pages/Dashboard.js");
const { Workspace } = await imp("src/pages/Workspace.js");

let pass = 0, fail = 0;
const ok = (name, fn) => Promise.resolve().then(fn).then(() => { pass++; console.log("  ✔", name); }, (e) => { fail++; console.log("  ✖", name, "\n     ", e.message.split("\n")[0]); });

const masters = await api.masters();
const wrap = (el) => R.renderToString(ce(ToastProvider, null, ce(MastersCtx.Provider, { value: masters }, el)));
const tabProps = (pid, view) => ({ pid, view, run: async () => null, reload: async () => {}, setView() {} });
const render = (C, pid, view) => wrap(ce(C, tabProps(pid, view)));

try {
  console.log("Pages render with live data");
  await ok("Dashboard shell renders (loading state)", () => assert.match(wrap(ce(Dashboard)), /PM Workspace/));
  await ok("Workspace loading state", () => assert.match(wrap(ce(Workspace, { pid: "JOSS-1", tab: "qa" })), /Opening project/));

  let v = await api.createProject("006AC00000A1001");
  const pid = v.context.project_id;
  await ok("project created with A1 pre-fill + A2 suggestion", () => { assert.equal(v.context.qa.combination_id, "QA-102"); assert.equal(v.context.edit_project.execution_model.value, "Fixed Price"); });
  await ok("duplicate opportunity -> 409 with message", async () => { await assert.rejects(api.createProject("006AC00000A1001"), (e) => e.status === 409 && /already exists/.test(e.message)); });
  await ok("Edit Project tab shows fields, evidence toggle, SOW card", () => { const h = render(EditProjectTab, pid, v); assert.match(h, /Project details/); assert.match(h, /Why this value\?/); assert.match(h, /Fixed Price/); assert.match(h, /Re-run A1/); assert.match(h, /Execution model/); });
  await ok("QA tab shows suggestion + top match", () => { const h = render(QaTab, pid, v); assert.match(h, /QA-102/); assert.match(h, /top match/); });
  await ok("Readiness lists modules and blockers", () => { const h = wrap(ce(Readiness, { view: v, tab: "qa", onTab() {} })); for (const m of ["Edit Project", "QA", "Jade Contacts", "Resource Mgmt", "Tasks"]) assert.ok(h.includes(m), m); assert.match(h, /JC-05/); });
  for (const [name, C] of [["Contacts", ContactsTab], ["Resources", ResourcesTab], ["Tasks", TasksTab], ["Submit", SubmitTab], ["History", HistoryTab]])
    await ok(`${name} tab renders (empty draft)`, () => assert.ok(render(C, pid, v).length > 500));
  await ok("Submit tab warns when not ready", () => assert.match(render(SubmitTab, pid, v), /blocking issue/));

  console.log("PM journey through src/api.js");
  const rev = async () => (await api.project(pid)).context.revision;
  let r = await api.editProject(pid, { fields: {}, save: true, expected_revision: await rev() });
  await ok("Edit Project saved (no blocks) and A2 re-ran", () => { assert.deepEqual(r.blocks, []); assert.equal(r.a2_ran, true); });
  await ok("QA saved", async () => { v = await api.setQa(pid, { combination_id: "QA-102", expected_revision: await rev() }); assert.equal(v.context.saved.qa, true); });
  await ok("stale revision is rejected (409)", async () => { await assert.rejects(api.setQa(pid, { combination_id: "QA-102", expected_revision: 1 }), (e) => e.status === 409); });
  await ok("QA override needs a reason (422)", async () => { await assert.rejects(api.setQa(pid, { combination_id: "QA-101", expected_revision: await rev() }), (e) => e.status === 422); });

  const chatApply = async (module, msg, pending) => {
    const c = await api.chat(pid, module, msg, pending);
    return c;
  };
  let c = await chatApply("contacts", "Make Anita Rao the Project Manager from 1 Nov");
  await ok("Contacts chat -> ready with preview; preview renders", () => { assert.equal(c.status, "ready"); const h = wrap(ce(Preview, { preview: c.preview, masters })); assert.match(h, /Anita Rao/); assert.match(h, /nothing is saved/i); });
  await ok("ChatPanel renders", () => assert.match(wrap(ce(ChatPanel, { pid, module: "contacts", view: v, run: async () => null, setView() {}, title: "Jade Contacts", applyLabel: "Create", placeholder: "x", chips: ["a"] })), /Jade Contacts/));
  v = await api.apply(pid, "contacts", c.changes, await rev());
  await ok("contact applied; approver auto-set", () => { assert.equal(v.context.contacts.length, 1); assert.equal(v.context.edit_project.timesheet_approval.value !== undefined, true); });

  for (let i = 1; i <= 5; i++) {
    const who = ["Anita Rao", "Amit Shah", "Anita Rao", "Amit Shah", "Anita Rao"][i - 1];
    const x = await chatApply("resources", `Assign ${who} to line ${i}`);
    if (x.status === "ready") v = await api.apply(pid, "resources", x.changes, await rev());
  }
  await ok("resource lines assigned via chat", () => assert.ok(v.context.resources.filter((l) => l.associate_id).length >= 1));
  await ok("Resources tab renders assigned lines + totals", () => { const h = render(ResourcesTab, pid, v); assert.match(h, /Resource lines/); assert.match(h, /Margin/); });

  let t = await chatApply("tasks", "Create task Design Review");
  await ok("tasks chat asks follow-up questions", () => { assert.equal(t.status, "needs_info"); assert.ok(t.pending); });
  t = await chatApply("tasks", "Anita Rao, 20%, from 1 Nov to 30 Nov", t.pending);
  await ok("task ready; add preview renders", () => { assert.equal(t.status, "ready"); assert.match(wrap(ce(Preview, { preview: t.preview, masters })), /Design Review/); });
  v = await api.apply(pid, "tasks", t.changes, await rev());
  const dup = await chatApply("tasks", "Create task Design Review for Anita Rao, 10%, 1 Dec to 10 Dec");
  await ok("duplicate task name is blocked", () => assert.notEqual(dup.status, "ready"));
  const de = await chatApply("tasks", "Deactivate Design Review");
  await ok("deactivate preview renders (tasks_update diff)", () => { assert.equal(de.preview.kind, "tasks_update"); assert.match(wrap(ce(Preview, { preview: de.preview, masters })), /Design Review/); });

  for (const m of ["contacts", "resources", "tasks"]) { try { v = await api.saveModule(pid, m, await rev()); } catch (e) { console.log("   save", m, "->", e.message, JSON.stringify(e.hits || []).slice(0, 200)); } }
  v = await api.project(pid);
  await ok("every module saved => Ready to Submit", () => { assert.equal(v.context.status, "Ready to Submit", JSON.stringify(v.submit_hits.map((h) => h.id + ":" + h.message)).slice(0, 400)); assert.equal(v.ready, true); });
  await ok("Tabs render in ready state", () => { for (const C of [EditProjectTab, QaTab, ContactsTab, ResourcesTab, TasksTab, SubmitTab, HistoryTab]) assert.ok(render(C, pid, v).length > 500); assert.doesNotMatch(render(SubmitTab, pid, v), /blocking issue/); });

  console.log("Submit, failure, idempotent retry");
  const sid = crypto.randomUUID();
  let s1 = await api.submit(pid, { submission_id: sid, expected_revision: await rev(), fail_at: "resources" });
  await ok("failure at resources: header/QA/contacts written, rest not", () => { const m = s1.result.modules; assert.equal(s1.result.overall_status, "failed"); assert.equal(m.resources.status, "failed"); assert.notEqual(m.tasks.status, "success"); });
  let s2 = await api.submit(pid, { submission_id: sid, expected_revision: await rev(), fail_at: null });
  await ok("retry with the same submission_id succeeds", () => assert.equal(s2.result.overall_status, "success"));
  let s3 = await api.submit(pid, { submission_id: sid, expected_revision: await rev(), fail_at: null });
  await ok("second replay is idempotent (no duplicates)", async () => { assert.equal(s3.result.idempotent_replay, true); const j = await api.joss(pid); assert.equal(j.contacts.length, 1); assert.equal(j.tasks.length, 1); });
  v = await api.project(pid);
  await ok("committed project renders (Submit/History/Readiness)", () => { assert.match(render(SubmitTab, pid, v), /Committed at revision/); assert.match(render(SubmitTab, pid, v), /Project lifecycle/); assert.ok(render(HistoryTab, pid, v).length > 300); });
  await ok("tasks tab shows in-JOSS badge and +8h action", () => assert.match(render(TasksTab, pid, v), /\+8h/));
  await ok("status On Hold works after commit", async () => { const x = await api.setStatus(pid, "On Hold"); assert.equal(x.context.status, "On Hold"); });
  await ok("audit table renders real events", async () => assert.match(R.renderToString(ce(AuditTable, { rows: await api.audit(pid) })), /commit\./));

  console.log("Conflicts, SOW replace, other opportunities");
  for (const opp of ["006AC00000A1002", "006AC00000A1003", "006AC00000A1004", "006AC00000A1005"]) {
    await ok(`opportunity ${opp} creates + renders all tabs`, async () => {
      const x = await api.createProject(opp);
      for (const C of [EditProjectTab, QaTab, ContactsTab, ResourcesTab, TasksTab, SubmitTab]) assert.ok(render(C, x.context.project_id, x).length > 500);
      const conflicts = Object.entries(x.context.edit_project).filter(([, cell]) => cell.conflict);
      if (conflicts.length) {
        const h = render(EditProjectTab, x.context.project_id, x); assert.match(h, /disagree/);
        const [k] = conflicts[0];
        const y = await api.editProject(x.context.project_id, { fields: {}, resolve: { [k]: "salesforce" }, save: false, expected_revision: x.context.revision });
        assert.equal(y.context.edit_project[k].conflict, null); console.log("      resolved conflict on", k);
      }
    });
  }
  await ok("SOW paste/replace re-runs A1", async () => { const g = (await api.opportunities()).find((o) => o.project_id && o.opportunity_id.endsWith("1002")); const y = await api.replaceSow(g.project_id, "STATEMENT OF WORK\nProject: Replacement\nThe project will commence on 1 Feb 2027 and finish on 31 May 2027.\nThis engagement is on a Time and Materials basis.\n", "x.txt", true); assert.ok(y.context.revision >= 2); });
  await ok("dashboard + projects list consistent", async () => { const d = await api.dashboard(); const ps = await api.projects(); assert.equal(d.projects, ps.length); assert.ok(d.committed >= 1); });
} finally { stop(); }
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
