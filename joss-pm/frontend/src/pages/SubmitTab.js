import { useState, useEffect } from "../../vendor/react.js";
import { h, ce, div, span, p, input, select, option, details, summary, pre, ul, li, label } from "../h.js";
import { api } from "../api.js";
import { Btn, Badge, Card, Modal, RuleList, useToast } from "../components/ui.js";
import { uuid, human, dateTime } from "../format.js";
import { getUser } from "../api.js";

const ORDER = [["project", "Project header"], ["qa", "QA profile"], ["contacts", "Jade contacts"], ["resources", "Resources"], ["tasks", "Tasks"]];
const ICON = { success: "✔", written: "✔", failed: "✖", skipped: "–", unchanged: "＝" };
const TONE = { success: "good", written: "good", failed: "bad", skipped: "neutral", unchanged: "info" };

function Result({ result }) {
  if (!result) return null;
  const ok = result.overall_status === "success";
  return div({ className: "result " + (ok ? "ok" : "bad") },
    div({ className: "result-head" }, ok ? "✔ Committed to JOSS" : "✖ Commit did not complete", result.idempotent_replay && Badge({ tone: "info" }, "replayed - already committed"),
      span({ className: "muted" }, ` · submission ${String(result.submission_id).slice(0, 8)} · revision ${result.revision}`)),
    ul({ className: "steps" }, ORDER.map(([k, lbl]) => { const m = (result.modules || {})[k] || { status: "skipped" };
      return li({ key: k, className: "step " + (TONE[m.status] || "neutral") },
        span({ className: "step-ico" }, ICON[m.status] || "•"), span({ className: "step-label" }, lbl), Badge({ tone: TONE[m.status] || "neutral" }, m.status),
        m.error && span({ className: "bad-t" }, m.error), m.detail && span({ className: "muted" }, typeof m.detail === "string" ? m.detail : JSON.stringify(m.detail))); })),
    (result.errors || []).length ? RuleList({ hits: result.errors.map((e) => ({ ...e, level: "BLOCK" })) }) : null,
    (result.warnings || []).length ? RuleList({ hits: result.warnings.map((e) => ({ ...e, level: "WARN" })) }) : null);
}

function PackageModal({ pid, onClose }) {
  const [pkg, setPkg] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.pkg(pid).then(setPkg, setErr); }, [pid]);
  const count = (v) => (Array.isArray(v) ? `${v.length} item(s)` : v && typeof v === "object" ? `${Object.keys(v).length} field(s)` : "");
  return ce(Modal, { title: "Submission package (what A6 will write)", onClose, wide: true },
    err ? div({ className: "banner bad" }, err.message) : !pkg ? p("Loading…") :
      div(p({ className: "muted" }, `Project ${pkg.project_id} · revision ${pkg.revision} · submitter ${pkg.submitter} · submission id ${pkg.submission_id || "assigned on submit"}`),
        Object.entries(pkg.modules || {}).map(([k, v]) => details({ key: k, open: k === "project" }, summary(span({ className: "b" }, human(k)), " ", span({ className: "muted" }, count(v))), pre({ className: "json" }, JSON.stringify(v, null, 2))))));
}

export function SubmitTab({ pid, view, run, reload }) {
  const toast = useToast();
  const ctx = view.context;
  const committed = view.committed_revision != null;
  const [subId, setSubId] = useState(() => uuid());
  const [result, setResult] = useState(null);
  const [failAt, setFailAt] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [pkgOpen, setPkgOpen] = useState(false);
  const [delegates, setDelegates] = useState((view.delegates || []).join(", "));
  const [att, setAtt] = useState(null);       // revision the pending submission id belongs to
  useEffect(() => { setDelegates((view.delegates || []).join(", ")); }, [view.delegates && view.delegates.join(",")]);

  const blockers = (view.submit_hits || []).filter((x) => x.level === "BLOCK");
  const canSubmit = view.ready && blockers.length === 0;

  async function doSubmit() {
    setConfirm(false);
    // New revision => new submission id; retry of the same failed revision keeps the id (idempotent, no duplicates).
    let id = subId;
    if (att !== null && att !== ctx.revision) { id = uuid(); setSubId(id); }
    setAtt(ctx.revision);
    const res = await run((rev) => api.submit(pid, { submission_id: id, expected_revision: rev, fail_at: failAt || null }), null);
    if (!res) return;
    setResult(res.result);
    if (res.result.overall_status === "success") { toast("Committed to JOSS", "good"); setSubId(uuid()); setAtt(null); setFailAt(""); }
    else toast("Commit did not complete - see details. Retrying is safe.", "bad");
  }
  const status = (s) => run(() => api.setStatus(pid, s), `Project is now ${s}`);
  const saveDelegates = () => run(() => api.setDelegates(pid, delegates.split(/[,;\s]+/).filter(Boolean)), "Delegates updated");

  const failedRetry = result && result.overall_status === "failed" && att === ctx.revision && Object.values(result.modules || {}).some((m) => m.status === "failed");
  return div({ className: "tab-body" },
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "Commit to JOSS (A6)" },
          committed && div({ className: "banner ok" }, `Committed at revision ${view.committed_revision}.`, view.pending_changes ? " You have newer changes that are not in JOSS yet - submit again to sync." : " JOSS is up to date."),
          !canSubmit && div({ className: "banner warn" }, blockers.length ? `${blockers.length} blocking issue(s) remain. Fix them in the module tabs (see the Readiness panel).` : "Save every module to make this project Ready to Submit."),
          blockers.length ? RuleList({ hits: blockers }) : null,
          div({ className: "row" },
            Btn({ onClick: () => setPkgOpen(true) }, "Review package"),
            Btn({ kind: "primary", disabled: !canSubmit, onClick: () => setConfirm(true) }, failedRetry ? "Retry submit" : committed ? "Submit changes to JOSS" : "Submit to JOSS")),
          p({ className: "muted" }, "Writes happen in order: project header → QA → contacts → resources → tasks. A6 re-runs every rule on the server; every attempt is audited and safe to retry."),
          details({ className: "demo" }, summary("Demo / UAT: simulate a JOSS write failure"),
            label("Fail at module: ", select({ value: failAt, onChange: (e) => setFailAt(e.target.value) }, option({ value: "" }, "none"), ORDER.map(([k, l]) => option({ key: k, value: k }, l))))),
          Result({ result })),
        committed && Card({ title: "Project lifecycle" },
          p("Current status: ", Badge({ tone: ctx.status === "Active" ? "good" : "warn" }, ctx.status)),
          div({ className: "row" }, ["Active", "On Hold", "Closed"].map((s) => Btn({ key: s, disabled: ctx.status === s, onClick: () => status(s) }, s))))),
      div({ className: "col side-col" },
        Card({ title: "Who can submit (X-04)" },
          p("Only the project's current Project Manager, the project owner, or a delegate."),
          p(span({ className: "diff-k" }, "Owner: "), view.owner_email), p(span({ className: "diff-k" }, "You: "), getUser()),
          label({ htmlFor: "deleg" }, "Delegates (emails, comma-separated)"),
          input({ id: "deleg", value: delegates, onChange: (e) => setDelegates(e.target.value), placeholder: "name@jadeglobal.com" }),
          div({ className: "row end" }, Btn({ onClick: saveDelegates }, "Save delegates"))))),
    confirm && ce(Modal, { title: "Commit to JOSS?", onClose: () => setConfirm(false) },
      p(`This writes revision ${ctx.revision} of ${ctx.project_id} to JOSS: header, QA, ${ctx.contacts.length} contact(s), ${ctx.resources.filter((r) => !r.released).length} resource line(s) and ${ctx.tasks.length} task(s).`),
      failAt && div({ className: "banner warn" }, "Demo fault injection is ON: the write will fail at " + failAt + "."),
      div({ className: "row end" }, Btn({ onClick: () => setConfirm(false) }, "Cancel"), Btn({ kind: "primary", onClick: doSubmit }, "Yes, commit"))),
    pkgOpen && ce(PackageModal, { pid, onClose: () => setPkgOpen(false) }));
}
