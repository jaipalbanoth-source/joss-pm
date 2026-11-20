import { h, ce, div, span, p, button, h1 } from "../h.js";
import { Badge, Btn, ErrorBox, Spinner, Tabs, STATUS_TONE } from "../components/ui.js";
import { Readiness } from "../components/Readiness.js";
import { useProject, useMasters } from "../state.js";
import { go } from "../state.js";
import { EditProjectTab } from "./EditProject.js";
import { QaTab } from "./QaTab.js";
import { ContactsTab } from "./ContactsTab.js";
import { ResourcesTab } from "./ResourcesTab.js";
import { TasksTab } from "./TasksTab.js";
import { SubmitTab } from "./SubmitTab.js";
import { HistoryTab } from "./HistoryTab.js";

const TABS = [["edit_project", "Edit Project"], ["qa", "QA"], ["contacts", "Jade Contacts"], ["resources", "Resource Mgmt"], ["tasks", "Tasks"], ["submit", "Submit"], ["history", "History"]];
const BODY = { edit_project: EditProjectTab, qa: QaTab, contacts: ContactsTab, resources: ResourcesTab, tasks: TasksTab, submit: SubmitTab, history: HistoryTab };

export function Workspace({ pid, tab }) {
  const { view, setView, error, busy, reload, run } = useProject(pid);
  if (error && !view) return div({ className: "page" }, ErrorBox({ error, onRetry: reload }), Btn({ onClick: () => go("/") }, "Back to dashboard"));
  if (!view) return div({ className: "page" }, Spinner({ label: "Opening project…" }));
  const ctx = view.context;
  const active = BODY[tab] ? tab : "edit_project";
  const mods = view.modules;
  const tabs = TABS.map(([key, label]) => {
    const m = mods[key];
    const badge = m ? (m.blocks ? span({ className: "dot bad", title: `${m.blocks} blocking` }) : m.ready ? span({ className: "dot ok", title: "ready" }) : span({ className: "dot pend", title: "not saved" })) : null;
    return { key, label, badge };
  });
  return div({ className: "workspace" },
    div({ className: "ws-head" },
      div(
        div({ className: "crumbs" }, button({ className: "link", onClick: () => go("/") }, "Projects"), " / ", ctx.project_id),
        h1(ctx.edit_project.project_name?.value || ctx.sf?.name || ctx.project_id),
        div({ className: "ws-meta" }, Badge({ tone: STATUS_TONE[ctx.status] || "neutral" }, ctx.status), span({ className: "muted" }, ` ${ctx.edit_project.customer_name?.value || ""} · Opp ${ctx.opportunity_id} · rev ${ctx.revision}`),
          view.pending_changes && Badge({ tone: "warn" }, "unsynced changes"))),
      div({ className: "ws-actions" }, busy && span({ className: "spin" }), Btn({ onClick: reload }, "Refresh"))),
    div({ className: "ws-grid" },
      aside(view, active),
      div({ className: "ws-main" },
        ce(Tabs, { tabs, active, onChange: (k) => go(`/p/${pid}/${k}`) }),
        ce(BODY[active], { key: pid + active, pid, view, run, reload, setView }))));

  function aside(v, act) {
    return div({ className: "ws-side" }, Readiness({ view: v, tab: act, onTab: (k) => go(`/p/${pid}/${k}`) }),
      Btn({ kind: "primary", className: "full", onClick: () => go(`/p/${pid}/submit`), disabled: false }, v.ready ? "Go to Submit →" : "Submit (not ready)"));
  }
}
