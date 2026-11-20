import { useState } from "../../vendor/react.js";
import { h, ce, div, span, p, table, thead, tbody, tr, th, td, button, h1, h2 } from "../h.js";
import { api } from "../api.js";
import { Btn, Badge, Card, Empty, ErrorBox, Spinner, RuleList, STATUS_TONE, useToast } from "../components/ui.js";
import { useAsync, go } from "../state.js";
import { money, pct, date, dateTime } from "../format.js";
import { AuditTable } from "./HistoryTab.js";

const Kpi = (n, l, tone) => div({ className: "kpi " + (tone || "") }, div({ className: "kpi-n" }, n), div({ className: "kpi-l" }, l));

export function Dashboard() {
  const toast = useToast();
  const dash = useAsync(() => api.dashboard(), []);
  const projects = useAsync(() => api.projects(), []);
  const opps = useAsync(() => api.opportunities(), []);
  const [creating, setCreating] = useState(null);
  const [dup, setDup] = useState(null);

  async function create(o) {
    setCreating(o.opportunity_id); setDup(null);
    try {
      const v = await api.createProject(o.opportunity_id);
      toast(`Created ${v.context.project_id} - A1 pre-filled the project from the SOW`, "good");
      go(`/p/${v.context.project_id}/edit_project`);
    } catch (e) {
      if (e.status === 409) setDup({ opp: o, message: e.message, hits: e.hits });
      else toast(e.message, "bad");
    } finally { setCreating(null); }
  }
  async function remove(pr) {
    if (!window.confirm(`Delete draft ${pr.project_id}? This cannot be undone.`)) return;
    try { await api.deleteProject(pr.project_id); toast("Draft deleted", "good"); projects.reload(); opps.reload(); dash.reload(); }
    catch (e) { toast(e.message, "bad"); }
  }
  const d = dash.data;
  return div({ className: "page" },
    div({ className: "page-head" }, h1("PM Workspace"), p({ className: "muted" }, "Create a JOSS project from a closed-won opportunity. Agents pre-fill from the SOW; you review, save each module and submit once.")),
    dash.error ? ErrorBox({ error: dash.error, onRetry: dash.reload }) : null,
    d && div({ className: "kpis wide" },
      Kpi(d.projects, "Projects"), Kpi(d.committed, "Committed to JOSS"), Kpi(pct(d.autofill_pct), "Fields auto-filled"),
      Kpi(d.qa_total ? pct(d.qa_acceptance_pct) : "-", "QA suggestions accepted"), Kpi(d.open_blocks, "Open blockers", d.open_blocks ? "bad" : "")),
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "My projects" }, projects.loading && !projects.data ? Spinner({}) : projects.data && projects.data.length ?
          h("table", { className: "grid" }, thead(tr(["Project", "Customer", "Status", "Modules", "Rev", "Updated", ""].map((c) => th({ key: c }, c)))),
            tbody(projects.data.map((pr) => tr({ key: pr.project_id },
              td(button({ className: "link b", onClick: () => go(`/p/${pr.project_id}/edit_project`) }, pr.project_id), div({ className: "muted" }, pr.name)),
              td(pr.customer), td(Badge({ tone: STATUS_TONE[pr.status] || "neutral" }, pr.status)),
              td(`${pr.modules_saved}/5 saved`, pr.blocks ? " " : "", pr.blocks ? Badge({ tone: "bad", title: "Blocking issues" }, pr.blocks) : null),
              td(pr.revision), td({ className: "muted" }, dateTime(pr.updated_at)),
              td(!pr.committed_revision && button({ className: "link", onClick: () => remove(pr) }, "Delete")))))) : Empty("No projects yet - create one from an opportunity.")),
        Card({ title: "Recent activity" }, d ? AuditTable({ rows: d.recent_audit }) : Spinner({}))),
      div({ className: "col side-col" },
        Card({ title: "Closed-won opportunities" },
          dup && div({ className: "banner warn" }, p(dup.message), p("Open the existing project instead:"), dup.hits && dup.hits.length ? RuleList({ hits: dup.hits }) : null,
            dup.opp.project_id && Btn({ onClick: () => go(`/p/${dup.opp.project_id}/edit_project`) }, "Open " + dup.opp.project_id)),
          opps.loading && !opps.data ? Spinner({}) : (opps.data || []).map((o) => div({ key: o.opportunity_id, className: "opp" },
            div({ className: "opp-main" }, div(span({ className: "b" }, o.name)), div({ className: "muted" }, `${o.account_name} · ${o.opportunity_id}`),
              div({ className: "muted" }, `${date(o.start_date)} → ${date(o.end_date)} · est. ${money(o.estimate_total)} · ${o.sow_filename ? "SOW attached" : "no SOW"}`)),
            o.project_id ? Btn({ onClick: () => go(`/p/${o.project_id}/edit_project`) }, "Open " + o.project_id) : Btn({ kind: "primary", busy: creating === o.opportunity_id, onClick: () => create(o) }, "Create project")))))));
}
