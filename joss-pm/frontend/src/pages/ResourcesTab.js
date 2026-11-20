import { h, ce, div, span, p, table, thead, tbody, tr, th, td, button } from "../h.js";
import { Card, Badge, Empty } from "../components/ui.js";
import { ChatPanel } from "../components/ChatPanel.js";
import { SaveBar } from "../components/SaveBar.js";
import { useMasters, nameOf } from "../state.js";
import { date, money, pct } from "../format.js";
import { useState } from "../../vendor/react.js";

export function ResourcesTab({ pid, view, run, setView }) {
  const masters = useMasters();
  const ctx = view.context;
  const [draft, setDraft] = useState(null);
  const t = ctx.totals, base = ctx.baseline;
  const lines = ctx.resources;
  const target = ctx.edit_project.margin_target?.value;
  const delta = t.budget - base.budget;
  return div({ className: "tab-body" },
    div({ className: "kpis wide" },
      div({ className: "kpi" }, div({ className: "kpi-n" }, money(t.budget)), div({ className: "kpi-l" }, "Budget", delta ? ` (${delta > 0 ? "+" : ""}${money(delta)} vs estimate)` : "")),
      div({ className: "kpi" }, div({ className: "kpi-n" }, money(t.cost)), div({ className: "kpi-l" }, "Cost")),
      div({ className: "kpi" }, div({ className: "kpi-n" }, money(t.hours)), div({ className: "kpi-l" }, "Hours")),
      div({ className: "kpi" + (target != null && t.margin_pct < target ? " bad" : "") }, div({ className: "kpi-n" }, pct(t.margin_pct)), div({ className: "kpi-l" }, target != null ? `Margin (target ${target}%)` : "Margin"))),
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "Resource lines" },
          lines.length ? div({ className: "scroll" }, h("table", { className: "grid dense" },
            thead(tr(["Line", "Role", "Level", "Loc.", "Qty", "Rate", "Hours", "Budget", "Associate", "Dates", "Alloc", ""].map((c) => th({ key: c }, c)))),
            tbody(lines.map((l) => tr({ key: l.id, className: l.released ? "released" : "" },
              td(l.id), td(span({ className: "b" }, l.role), div({ className: "muted" }, l.technology)), td(l.level), td(l.location), td(l.qty), td(l.bill_rate), td(money(l.hours)), td(money(l.budget)),
              td(l.associate_id ? nameOf(masters, l.associate_id) : Badge({ tone: "bad" }, "unassigned")),
              td(date(l.start), " → ", date(l.end)), td(l.allocation_pct != null ? l.allocation_pct + "%" : "-"),
              td(l.released ? Badge({ tone: "neutral" }, "released") : l.source === "pm" && Badge({ tone: "info" }, "added"), l.committed && Badge({ tone: "neutral" }, "in JOSS")),
            )))))  : Empty("No resource lines.")),
        ce(SaveBar, { pid, module: "resources", view, run })),
      div({ className: "col side-col" },
        Card({ title: "Resource agent (A5)" },
          ce(ChatPanel, { pid, module: "resources", view, run, setView, title: "Resource Mgmt", applyLabel: "Apply", draft,
            placeholder: "e.g. Assign Amit Shah to line 2",
            chips: ["Assign Anita Rao to line 1", "Add a Developer TE3 offshore for 400 hours", "Split line 4 into two", "Release line 5"] })))));
}
