import { h, div, span, table, thead, tbody, tr, th, td, p } from "../h.js";
import { Badge } from "./ui.js";
import { date, human } from "../format.js";
import { nameOf } from "../state.js";

function show(masters, k, v) {
  if (v === null || v === undefined || v === "") return "-";
  if (k.endsWith("associate_id") || k === "assignee_id") return nameOf(masters, v);
  if (k === "start" || k === "end" || k.endsWith("_date")) return date(v);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
}
const keyLabel = (k) => human(k.replace(/_id$/, ""));

function DiffCell({ masters, before, after }) {
  const keys = Object.keys(after || {}).filter((k) => JSON.stringify((before || {})[k]) !== JSON.stringify(after[k]));
  if (!keys.length) return span({ className: "muted" }, "no change");
  return div({ className: "diff" }, keys.map((k) => div({ key: k },
    span({ className: "diff-k" }, keyLabel(k) + ": "), span({ className: "diff-old" }, show(masters, k, (before || {})[k])), " → ",
    span({ className: "diff-new" }, show(masters, k, after[k])))));
}

/** Human-readable preview of exactly what the agent will write if the PM clicks Create / Update / Apply. */
export function Preview({ preview, masters }) {
  if (!preview) return null;
  const k = preview.kind;
  let body = null;
  if (k === "contacts") {
    body = h("table", { className: "grid" },
      thead(tr(["Action", "Role", "Associate", "Start", "End", "Previously"].map((c) => th({ key: c }, c)))),
      tbody(preview.rows.map((r, i) => tr({ key: i }, td(Badge({ tone: r.action === "CREATE" ? "good" : r.action === "END" ? "warn" : "info" }, r.action)),
        td(r.role), td(r.associate), td(date(r.start)), td(r.end ? date(r.end) : "-"), td({ className: "muted" }, r.was || "")))));
  } else if (k === "tasks_add") {
    body = h("table", { className: "grid" },
      thead(tr(["Task", "Assignee", "Util %", "Start", "End", "Billable", "Active"].map((c) => th({ key: c }, c)))),
      tbody(preview.tasks.map((t, i) => tr({ key: i }, td(t.name), td(nameOf(masters, t.assignee_id)), td(t.utilization), td(date(t.start)), td(date(t.end)),
        td(t.billable ? "Yes" : "No"), td(t.active === false ? "No" : "Yes")))));
  } else if (k === "tasks_update") {
    body = h("table", { className: "grid" }, thead(tr(th("Task"), th("Change"))),
      tbody(preview.diff.map((d, i) => tr({ key: i }, td(d.name), td(DiffCell({ masters, before: d.before, after: d.after }))))));
  } else if (k === "resources") {
    body = h("table", { className: "grid" }, thead(tr(th("Line"), th("Change"))),
      tbody(preview.rows.map((r, i) => tr({ key: i }, td(r.line_id, " ", r.new && Badge({ tone: "info" }, "new line")), td(DiffCell({ masters, before: r.before || {}, after: r.after || {} }))))));
  } else {
    body = div({ className: "kv" }, Object.entries(preview).filter(([k2]) => k2 !== "kind").map(([k2, v]) => div({ key: k2 }, span({ className: "diff-k" }, keyLabel(k2) + ": "), typeof v === "object" ? JSON.stringify(v) : String(v))));
  }
  return div({ className: "preview" },
    div({ className: "preview-title" }, "Preview – nothing is saved until you confirm"),
    body,
    preview.approver_change && p({ className: "note" }, "Also sets timesheet approver in Edit Project to ", span({ className: "b" }, preview.approver_change), "."),
    preview.impact && p({ className: "note" }, "Impact: ", preview.impact));
}
