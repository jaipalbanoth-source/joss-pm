import { useState } from "../../vendor/react.js";
import { div, span, p } from "../h.js";
import { api, ApiError } from "../api.js";
import { Btn, Badge, RuleList, useToast } from "./ui.js";

/** "Save module" - marks the module's draft as saved after re-validating it against the module's rules. */
export function SaveBar({ pid, module, view, run }) {
  const toast = useToast();
  const [hits, setHits] = useState([]);
  const m = view.modules[module];
  async function save() {
    setHits([]);
    const res = await run(async (rev) => {
      try { return await api.saveModule(pid, module, rev); }
      catch (e) { if (e instanceof ApiError && e.hits && e.hits.length) setHits(e.hits); throw e; }
    }, null);
    if (res) toast(`${m.label} saved`, "good");
  }
  const own = (view.submit_hits || []).filter((h) => h.module === module);
  return div({ className: "savebar" },
    div({ className: "savebar-state" },
      m.saved ? Badge({ tone: "good" }, "Saved") : Badge({ tone: "warn" }, "Not saved"),
      own.some((h) => h.level === "BLOCK") ? span({ className: "bad-t" }, ` ${own.filter((h) => h.level === "BLOCK").length} issue(s) must be fixed before submit`) : span({ className: "ok-t" }, " no blocking issues")),
    Btn({ kind: "primary", onClick: save }, `Save ${m.label}`),
    hits.length ? RuleList({ hits }) : null);
}
