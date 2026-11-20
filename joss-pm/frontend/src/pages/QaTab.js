import { useState, useEffect } from "../../vendor/react.js";
import { h, ce, div, span, p, label, input, textarea, table, thead, tbody, tr, th, td, ul, li } from "../h.js";
import { api } from "../api.js";
import { Btn, Badge, Card, Empty, confTone } from "../components/ui.js";
import { useMasters } from "../state.js";
import { useAsync } from "../state.js";
import { SaveBar } from "../components/SaveBar.js";
import { dateTime } from "../format.js";

export function QaTab({ pid, view, run }) {
  const masters = useMasters();
  const qa = view.context.qa;
  const sugg = qa.suggestions || [];
  const topId = sugg[0]?.combination_id;
  const [choice, setChoice] = useState(qa.combination_id || "");
  const [reason, setReason] = useState(qa.reason || "");
  useEffect(() => { setChoice(qa.combination_id || ""); setReason(qa.reason || ""); }, [qa.combination_id, qa.reason]);
  const overriding = !!topId && !!choice && choice !== topId;
  const cur = (masters.qa_master || []).find((q) => q.combination_id === qa.combination_id);
  const overrides = useAsync(() => api.qaOverrides(pid), [pid, view.context.revision]);
  const sig = view.context.a1?.qa_signals || {};

  const save = () => run((rev) => api.setQa(pid, { combination_id: choice, reason: overriding ? reason : null, expected_revision: rev }), "QA combination saved");
  return div({ className: "tab-body" },
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "QA combination (A2 suggestion)" },
          qa.combination_id ? div({ className: "qa-current" },
            div(span({ className: "b" }, qa.combination_id), " · ", cur ? cur.label : ""),
            div(qa.overridden ? Badge({ tone: "warn" }, "PM override") : Badge({ tone: "good" }, "A2 suggestion"), " ",
              qa.score != null && Badge({ tone: confTone(qa.score) }, `score ${Math.round(qa.score * 100)}%`))) : p({ className: "muted" }, "No combination selected yet."),
          !qa.threshold_met && div({ className: "banner warn" }, "A2 could not find a confident match (best score " + Math.round((qa.best_score || 0) * 100) + "%). Please choose manually."),
          (qa.warnings || []).map((w, i) => div({ key: i, className: "banner warn" }, String(w))),
          sugg.length ? div({ className: "sugg" }, sugg.map((s, i) =>
            label({ key: s.combination_id, className: "sugg-row" + (choice === s.combination_id ? " on" : "") },
              input({ type: "radio", name: "qa", checked: choice === s.combination_id, onChange: () => setChoice(s.combination_id) }),
              div({ className: "sugg-main" },
                div(span({ className: "b" }, s.combination_id), " ", s.label, i === 0 && " ", i === 0 && Badge({ tone: "info" }, "top match")),
                div({ className: "muted" }, (s.reasons || []).join(" · "))),
              Badge({ tone: confTone(s.score) }, Math.round(s.score * 100) + "%")))) : null,
          div({ className: "field" },
            label({ htmlFor: "qa-any" }, "Or pick any combination from the QA master"),
            h("select", { id: "qa-any", value: choice, onChange: (e) => setChoice(e.target.value) },
              h("option", { value: "" }, "Select…"), (masters.qa_master || []).map((q) => h("option", { key: q.combination_id, value: q.combination_id }, `${q.combination_id} – ${q.label}`)))),
          overriding && div({ className: "field attn" },
            label({ htmlFor: "qa-reason" }, "Reason for overriding the suggestion ", span({ className: "req" }, "*")),
            textarea({ id: "qa-reason", rows: 2, value: reason, onChange: (e) => setReason(e.target.value), placeholder: "e.g. Client confirmed a waterfall delivery model" })),
          div({ className: "row end" }, Btn({ kind: "primary", onClick: save, disabled: !choice || (overriding && !reason.trim()) }, "Save QA combination"))),
        ce(SaveBar, { pid, module: "qa", view, run })),
      div({ className: "col side-col" },
        Card({ title: "Signals A1 read from the SOW" },
          Object.keys(sig).length ? ul({ className: "plain" }, Object.entries(sig).map(([k, v]) => li({ key: k }, span({ className: "diff-k" }, k.replace(/_/g, " ") + ": "), Array.isArray(v) ? v.join(", ") || "-" : String(v ?? "-")))) : Empty("No signals extracted.")),
        Card({ title: "Override history" },
          overrides.data && overrides.data.length ? ul({ className: "plain" }, overrides.data.map((o) => li({ key: o.id }, `${o.suggested} → ${o.chosen}`, div({ className: "muted" }, `${o.reason || ""} · ${dateTime(o.ts)}`)))) : Empty("No overrides.")))));
}
