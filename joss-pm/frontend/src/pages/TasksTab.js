import { h, ce, div, span, table, thead, tbody, tr, th, td, button } from "../h.js";
import { Card, Badge, Empty, useToast } from "../components/ui.js";
import { ChatPanel } from "../components/ChatPanel.js";
import { SaveBar } from "../components/SaveBar.js";
import { useMasters, nameOf } from "../state.js";
import { api } from "../api.js";
import { date } from "../format.js";
import { useState } from "../../vendor/react.js";

export function TasksTab({ pid, view, run, setView }) {
  const masters = useMasters();
  const toast = useToast();
  const ctx = view.context;
  const [draft, setDraft] = useState(null);
  const prefill = (text) => setDraft({ text, nonce: Math.random() });
  const pool = view.pool || {};
  const poolNames = Object.keys(pool).map((id) => nameOf(masters, id));
  const hours = async (t) => { const r = await run(() => api.simulateHours(pid, t.id, 8).then(() => api.project(pid)), null); if (r) toast(`Logged 8h on "${t.name}" (simulated timesheet)`, "good"); };
  return div({ className: "tab-body" },
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "Tasks" },
          ctx.tasks.length ? div({ className: "scroll" }, h("table", { className: "grid" },
            thead(tr(["Task", "Assignee", "Util %", "Start", "End", "Billable", "Status", ""].map((c) => th({ key: c }, c)))),
            tbody(ctx.tasks.map((t) => tr({ key: t.id, className: t.active ? "" : "released" },
              td(span({ className: "b" }, t.name)), td(nameOf(masters, t.assignee_id)), td(t.utilization), td(date(t.start)), td(date(t.end)), td(t.billable ? "Yes" : "No"),
              td(t.active ? Badge({ tone: "good" }, "active") : Badge({ tone: "neutral" }, "inactive"), t.has_logged_hours && " ", t.has_logged_hours && Badge({ tone: "info", title: "Tasks with logged hours can only be deactivated" }, "hours logged"), t.committed && " ", t.committed && Badge({ tone: "neutral" }, "in JOSS")),
              td({ className: "nowrap" },
                button({ className: "link", onClick: () => prefill(t.active ? `Deactivate ${t.name}` : `Reactivate ${t.name}`) }, t.active ? "Deactivate" : "Reactivate"), " ",
                t.committed && button({ className: "link", title: "Demo: simulate a timesheet entry (rule TK-06)", onClick: () => hours(t) }, "+8h"))))))) :
            Empty("No tasks yet. Describe your first task in the chat on the right."),
          poolNames.length ? div({ className: "muted pad" }, "Assignee pool (contacts + resourced associates): ", poolNames.join(", ")) : div({ className: "muted pad" }, "The assignee pool fills up once contacts and resources are assigned.")),
        ce(SaveBar, { pid, module: "tasks", view, run })),
      div({ className: "col side-col" },
        Card({ title: "Task agent (A3)" },
          ce(ChatPanel, { pid, module: "tasks", view, run, setView, title: "Tasks", applyLabel: "Create", draft,
            placeholder: "e.g. Create task Design Review for Anita Rao, 20%, 1 Nov to 30 Nov",
            chips: ["Create task Design Review", "Create tasks Build and Test for Amit Shah at 50% from 1 Dec to 31 Jan", "Change Design Review end date to 15 Dec"] })))));
}
