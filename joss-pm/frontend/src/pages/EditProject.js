import { useState, useEffect } from "../../vendor/react.js";
import { h, ce, div, span, input, select, option, textarea, label, button, p, small, details, summary, pre } from "../h.js";
import { api } from "../api.js";
import { Btn, Badge, Card, Modal, RuleList, STATE_META, confTone, useToast } from "../components/ui.js";
import { useMasters } from "../state.js";
import { date, pct } from "../format.js";

const READONLY = new Set(["process_status", "active_yn", "sales_margin"]);

function Editor({ f, value, onChange, masters, disabled }) {
  const common = { id: "f-" + f.key, value: value ?? "", disabled, onChange: (e) => onChange(e.target.value) };
  if (f.type === "textarea") return textarea({ ...common, rows: 4 });
  if (f.type === "date") return input({ ...common, type: "date" });
  if (f.type === "number") return input({ ...common, type: "number", step: "any" });
  if (f.type === "yn") return select(common, option({ value: "" }, "—"), option({ value: "Y" }, "Yes"), option({ value: "N" }, "No"));
  if (f.type === "status") return select(common, (masters.process_statuses || []).map((s) => option({ key: s, value: s }, s)));
  if (f.type === "select") return select(common, option({ value: "" }, "Select…"), Object.keys(masters.execution_models || {}).map((s) => option({ key: s, value: s }, s)));
  if (f.key === "customer_name") return div(input({ ...common, list: "customers" }), h("datalist", { id: "customers" }, (masters.customers || []).map((c) => option({ key: c, value: c }))));
  return input({ ...common, type: "text" });
}

function FieldRow({ f, cell, draft, setDraft, masters, onResolve, busy }) {
  const [open, setOpen] = useState(false);
  const [tone, tip] = STATE_META[cell.state] || ["neutral", cell.state];
  const ro = READONLY.has(f.key);
  const dirty = draft !== undefined && String(draft) !== String(cell.value ?? "");
  const shown = draft !== undefined ? draft : cell.value;
  return div({ className: "field" + (cell.state === "missing" || cell.state === "conflict" ? " attn" : "") },
    div({ className: "field-top" },
      label({ htmlFor: "f-" + f.key }, f.label, f.mandatory && span({ className: "req", title: "Mandatory" }, " *")),
      div({ className: "field-badges" },
        dirty && Badge({ tone: "warn" }, "edited"),
        Badge({ tone, title: tip }, cell.state === "high" || cell.state === "review" || (cell.confidence != null && cell.origin === "sow") ? `${tip} · ${Math.round((cell.confidence || 0) * 100)}%` : tip))),
    Editor({ f, value: shown, onChange: (v) => setDraft(f.key, v), masters, disabled: ro || busy }),
    cell.conflict && div({ className: "conflict" },
      p("The SOW and Salesforce disagree - pick the right value:"),
      div({ className: "conflict-opts" },
        Btn({ onClick: () => onResolve(f.key, "sow"), busy }, `Use SOW: ${f.type === "date" ? date(cell.conflict.sow_value) : cell.conflict.sow_value}`),
        Btn({ onClick: () => onResolve(f.key, "salesforce"), busy }, `Use Salesforce (${cell.conflict.salesforce_field}): ${f.type === "date" ? date(cell.conflict.salesforce_value) : cell.conflict.salesforce_value}`))),
    (cell.source || cell.evidence) && div({ className: "why" },
      button({ className: "link", onClick: () => setOpen(!open), "aria-expanded": open }, open ? "Hide source" : "Why this value?"),
      open && div({ className: "evidence" }, cell.source && div(span({ className: "diff-k" }, "Source: "), cell.source), cell.evidence && div({ className: "quote" }, cell.evidence), cell.note && div(cell.note))));
}

function SowModal({ pid, onClose, onDone, run }) {
  const [sow, setSow] = useState(null);
  const [mode, setMode] = useState("view");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [keep, setKeep] = useState(true);
  useEffect(() => { api.sow(pid).then(setSow, () => setSow({ filename: "(none)", text: "" })); }, [pid]);
  async function replace() {
    const res = await run(() => file ? api.uploadSow(pid, file) : api.replaceSow(pid, text, "pasted-sow.txt", keep), "SOW replaced - A1 re-ran");
    if (res) onDone();
  }
  return ce(Modal, { title: "Statement of Work", onClose, wide: true },
    div({ className: "seg" }, ["view", "replace"].map((m) => button({ key: m, className: "seg-b" + (mode === m ? " on" : ""), onClick: () => setMode(m) }, m === "view" ? "View SOW" : "Upload / replace"))),
    mode === "view" ? div(p({ className: "muted" }, sow ? `${sow.filename} · ${sow.source || ""}` : "Loading…"), pre({ className: "sow-text" }, sow ? sow.text : "")) :
      div({ className: "col" },
        p("Upload a .txt, .pdf or .docx, or paste text. A1 re-extracts the fields; fields you already confirmed are kept unless you untick below."),
        input({ type: "file", accept: ".txt,.pdf,.docx", onChange: (e) => setFile(e.target.files[0] || null), "aria-label": "SOW file" }),
        textarea({ rows: 10, placeholder: "…or paste SOW text here", value: text, onChange: (e) => setText(e.target.value) }),
        label({ className: "check" }, input({ type: "checkbox", checked: keep, onChange: (e) => setKeep(e.target.checked) }), " Keep my edits (don't overwrite PM-confirmed fields)"),
        Btn({ kind: "primary", onClick: replace, disabled: !file && text.trim().length < 20 }, "Replace SOW and re-run A1")));
}

export function EditProjectTab({ pid, view, run, reload }) {
  const masters = useMasters();
  const toast = useToast();
  const ctx = view.context;
  const [draft, setDraftState] = useState({});
  const [blocks, setBlocks] = useState([]);
  const [sowOpen, setSowOpen] = useState(false);
  const [keep, setKeep] = useState(true);
  useEffect(() => { setDraftState({}); }, [ctx.project_id]);
  const setDraft = (k, v) => setDraftState((d) => ({ ...d, [k]: v }));

  const dirtyFields = () => Object.fromEntries(Object.entries(draft).filter(([k, v]) => String(v) !== String(ctx.edit_project[k]?.value ?? "")));
  async function submit(save) {
    const res = await run((rev) => api.editProject(pid, { fields: dirtyFields(), save, expected_revision: rev }), null);
    if (!res) return;
    setDraftState({}); setBlocks(res.blocks || []);
    if (save) res.blocks && res.blocks.length ? toast("Not saved - fix the highlighted issues first.", "bad") : toast("Edit Project saved. A2 re-checked the QA combination.", "good");
    else toast("Draft updated.", "good");
  }
  const resolve = (k, pick) => run((rev) => api.editProject(pid, { fields: {}, resolve: { [k]: pick }, save: false, expected_revision: rev }), "Conflict resolved");
  const rerun = () => run(() => api.rerunA1(pid, keep), "A1 re-ran on the current SOW");

  const a1 = ctx.a1 || {};
  const nDirty = Object.keys(dirtyFields()).length;
  return div({ className: "tab-body" },
    div({ className: "two-col" },
      div({ className: "col main-col" },
        Card({ title: "Project details", actions: [
            Btn({ key: "u", onClick: () => submit(false), disabled: !nDirty, busy: false }, "Update draft"),
            Btn({ key: "s", kind: "primary", onClick: () => submit(true), busy: false }, ctx.saved.edit_project && !nDirty ? "Re-save" : "Save Edit Project")] },
          blocks.length ? RuleList({ hits: blocks }) : null,
          div({ className: "fields" }, masters.edit_fields.map((f) =>
            ctx.edit_project[f.key] ? ce(FieldRow, { key: f.key, f, cell: ctx.edit_project[f.key], draft: draft[f.key], setDraft, masters, onResolve: resolve, busy: false }) : null)))),
      div({ className: "col side-col" },
        Card({ title: "Statement of Work (A1)", actions: Btn({ onClick: () => setSowOpen(true) }, "View / replace") },
          p(span({ className: "b" }, "Opportunity "), ctx.opportunity_id),
          p(span({ className: "b" }, "Salesforce "), `${ctx.sf?.account_name} · ${date(ctx.sf?.start_date)} → ${date(ctx.sf?.end_date)}`),
          (a1.warnings || []).map((w, i) => div({ key: i, className: "banner warn" }, String(w))),
          (a1.errors || []).map((w, i) => div({ key: i, className: "banner bad" }, String(w))),
          div({ className: "row" }, Btn({ onClick: rerun }, "Re-run A1"),
            label({ className: "check" }, input({ type: "checkbox", checked: keep, onChange: (e) => setKeep(e.target.checked) }), " keep my edits"))),
        Card({ title: "Commercials (from Resource Mgmt)" },
          div({ className: "kpis" },
            div({ className: "kpi" }, div({ className: "kpi-n" }, Math.round(ctx.totals.budget).toLocaleString()), div({ className: "kpi-l" }, "Budget")),
            div({ className: "kpi" }, div({ className: "kpi-n" }, Math.round(ctx.totals.cost).toLocaleString()), div({ className: "kpi-l" }, "Cost")),
            div({ className: "kpi" }, div({ className: "kpi-n" }, pct(ctx.totals.margin_pct)), div({ className: "kpi-l" }, "Margin"))),
          p({ className: "muted" }, "Sales margin is derived from the resource estimate and shown read-only.")))),
    sowOpen && ce(SowModal, { pid, run, onClose: () => setSowOpen(false), onDone: () => { setSowOpen(false); setDraftState({}); } }));
}
