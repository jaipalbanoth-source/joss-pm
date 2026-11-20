import { useState } from "../../vendor/react.js";
import { h, ce, div, span, p, table, thead, tbody, tr, th, td, button } from "../h.js";
import { Card, Badge, Empty } from "../components/ui.js";
import { ChatPanel } from "../components/ChatPanel.js";
import { SaveBar } from "../components/SaveBar.js";
import { useMasters, nameOf } from "../state.js";
import { date } from "../format.js";

export function ContactsTab({ pid, view, run, setView }) {
  const masters = useMasters();
  const ctx = view.context;
  const today = ctx.today || new Date().toISOString().slice(0, 10);
  const [draft, setDraft] = useState(null);
  const status = (c) => (c.end && c.end < today ? ["neutral", "ended"] : c.start > today ? ["info", "future"] : ["good", "active"]);
  const prefill = (text) => setDraft({ text, nonce: Math.random() });
  const approver = ctx.timesheet_approver_id;
  return div({ className: "tab-body" },
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "Jade contacts on this project" },
          ctx.contacts.length ? h("table", { className: "grid" },
            thead(tr(["Role", "Associate", "Start", "End", "Status", ""].map((c) => th({ key: c }, c)))),
            tbody(ctx.contacts.map((c) => { const [tone, label] = status(c); return tr({ key: c.id },
              td(span({ className: "b" }, c.role), masters.contact_roles[c.role] && span({ className: "muted" }, " (single holder)")),
              td(nameOf(masters, c.associate_id)), td(date(c.start)), td(c.end ? date(c.end) : "open-ended"),
              td(Badge({ tone }, label), c.committed && " ", c.committed && Badge({ tone: "neutral" }, "in JOSS")),
              td(!(c.end && c.end < today) && button({ className: "link", onClick: () => prefill(`End ${nameOf(masters, c.associate_id)} as ${c.role} on `) }, "End…"))); }))) : Empty("No contacts yet. Start with the Project Manager."),
          approver && p({ className: "muted pad" }, "Timesheet approver: ", span({ className: "b" }, nameOf(masters, approver)))),
        ce(SaveBar, { pid, module: "contacts", view, run })),
      div({ className: "col side-col" },
        Card({ title: "Contacts agent (A4)" },
          ce(ChatPanel, { pid, module: "contacts", view, run, setView, title: "Jade Contacts", applyLabel: "Create", draft,
            placeholder: "e.g. Make Anita Rao the Project Manager from 1 Nov",
            chips: ["Make Anita Rao the Project Manager from 1 Nov", "Hand over Project Manager to Rahul from 1 Jan", "Add Amit Shah as Tech Lead from 15 Nov"] })))));
}
