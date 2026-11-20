import { useState } from "../../vendor/react.js";
import { h, ce, div, span, p, table, thead, tbody, tr, th, td, button, pre, details, summary } from "../h.js";
import { api } from "../api.js";
import { Card, Badge, Empty, Modal, Spinner } from "../components/ui.js";
import { useAsync } from "../state.js";
import { dateTime, human } from "../format.js";

function RevModal({ pid, rev, onClose }) {
  const { data, error } = useAsync(() => api.revision(pid, rev), [pid, rev]);
  return ce(Modal, { title: `Revision ${rev}`, onClose, wide: true }, error ? p(error.message) : !data ? Spinner({}) :
    div(p({ className: "muted" }, `${data.note || ""} · ${data.saved_by} · ${dateTime(data.ts)}`), pre({ className: "json" }, JSON.stringify(data.context, null, 2))));
}

export function AuditTable({ rows }) {
  if (!rows || !rows.length) return Empty("No events yet.");
  return div({ className: "scroll" }, h("table", { className: "grid dense" }, thead(tr(["When", "Actor", "Action", "Module", "Detail"].map((c) => th({ key: c }, c)))),
    tbody(rows.map((r) => tr({ key: r.id }, td({ className: "nowrap" }, dateTime(r.ts)), td(r.actor.startsWith("agent:") ? Badge({ tone: "info" }, r.actor) : r.actor), td(span({ className: "b" }, r.action)), td(r.module || ""),
      td(details(summary({ className: "muted" }, "view"), pre({ className: "json small" }, JSON.stringify(r.detail, null, 2)))))))));
}

export function HistoryTab({ pid, view }) {
  const rev = useAsync(() => api.revisions(pid), [pid, view.context.revision]);
  const audit = useAsync(() => api.audit(pid, 300), [pid, view.context.revision]);
  const joss = useAsync(() => api.joss(pid), [pid, view.context.revision]);
  const [open, setOpen] = useState(null);
  const j = joss.data;
  return div({ className: "tab-body" },
    div({ className: "two-col" },
      div({ className: "col main-col" }, Card({ title: "Audit log" }, audit.loading && !audit.data ? Spinner({}) : AuditTable({ rows: audit.data }))),
      div({ className: "col side-col" },
        Card({ title: "Revisions" }, rev.data && rev.data.length ? h("table", { className: "grid dense" }, tbody(rev.data.map((r) => tr({ key: r.revision },
          td(span({ className: "b" }, "r" + r.revision), view.committed_revision === r.revision && " ", view.committed_revision === r.revision && Badge({ tone: "good" }, "in JOSS")),
          td(r.note, div({ className: "muted" }, dateTime(r.ts) + " · " + r.saved_by)), td(button({ className: "link", onClick: () => setOpen(r.revision) }, "view")))))) : Empty("No revisions.")),
        Card({ title: "What is in JOSS (simulated)" }, !j ? Spinner({}) : !j.project ? Empty("Nothing committed yet.") :
          div(p(span({ className: "b" }, j.project.project_name || j.project.project_id), " · ", j.project.process_status),
            p({ className: "muted" }, `${j.qa ? "QA " + j.qa.combination_id + " · " : ""}${j.contacts.length} contacts · ${j.resources.length} resources · ${j.tasks.length} tasks`),
            details(summary("Submissions (" + j.submissions.length + ")"), j.submissions.map((s) => div({ key: s.submission_id, className: "muted" }, `${dateTime(s.ts)} · r${s.revision} · ${s.status}`))))))),
    open && ce(RevModal, { pid, rev: open, onClose: () => setOpen(null) }));
}
