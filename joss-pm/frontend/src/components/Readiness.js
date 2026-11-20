import { h, div, span, button, ul, li, p } from "../h.js";
import { RuleList, Badge, STATUS_TONE } from "./ui.js";

const ICON = (m) => (m.ready ? "✔" : m.blocks ? "✖" : m.saved ? "◐" : "○");

/** Readiness checklist: one row per module + the live rule engine output (same rules A6 re-checks at submit). */
export function Readiness({ view, tab, onTab }) {
  const mods = view.modules;
  const hits = view.submit_hits || [];
  const sum = view.hits_summary || { block: 0, warn: 0 };
  return div({ className: "readiness" },
    div({ className: "ready-head" },
      span({ className: "ready-title" }, "Readiness"),
      Badge({ tone: STATUS_TONE[view.context.status] || "neutral" }, view.context.status)),
    ul({ className: "ready-list" }, Object.entries(mods).map(([k, m]) =>
      li({ key: k },
        button({ className: "ready-row" + (tab === k ? " active" : ""), onClick: () => onTab(k) },
          span({ className: "ready-ico " + (m.ready ? "ok" : m.blocks ? "bad" : "pend") }, ICON(m)),
          span({ className: "ready-label" }, m.label),
          span({ className: "ready-meta" }, m.ready ? "ready" : !m.saved ? "not saved" : "saved"),
          m.blocks ? Badge({ tone: "bad", title: "Blocking issues" }, m.blocks) : null,
          m.warns ? Badge({ tone: "warn", title: "Warnings" }, m.warns) : null)))),
    div({ className: "ready-sum" }, sum.block ? span({ className: "bad-t" }, `${sum.block} blocking`) : span({ className: "ok-t" }, "No blockers"),
      sum.warn ? span({ className: "warn-t" }, ` · ${sum.warn} warning${sum.warn > 1 ? "s" : ""}`) : null),
    hits.length ? div({ className: "ready-issues" }, RuleList({ hits })) : p({ className: "muted" }, "All checks pass."));
}
