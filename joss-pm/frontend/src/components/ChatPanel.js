import { useState, useEffect, useRef } from "../../vendor/react.js";
import { h, div, span, button, textarea, form, p } from "../h.js";
import { api } from "../api.js";
import { Btn, RuleList, useToast, Badge } from "./ui.js";
import { Preview } from "./Preview.js";
import { useMasters } from "../state.js";

/**
 * Generic agent chat (A3 Tasks, A4 Contacts, A5 Resources). The agents are stateless: the client keeps `pending`
 * (the half-filled draft) and sends it back with every turn.  Writes only happen when the PM clicks the apply button.
 */
export function ChatPanel({ pid, module, view, run, setView, title, applyLabel, placeholder, chips = [], draft }) {
  const masters = useMasters();
  const toast = useToast();
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [pending, setPending] = useState(null);
  const [cur, setCur] = useState(null);       // last agent response (preview + changes)
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    let live = true;
    setMsgs([]); setPending(null); setCur(null);
    api.chatHistory(pid, module).then((hs) => live && setMsgs(hs.map((x) => ({ role: x.role, content: x.content }))), () => {});
    return () => { live = false; };
  }, [pid, module]);
  useEffect(() => { endRef.current && endRef.current.scrollIntoView({ block: "nearest" }); }, [msgs, cur]);
  useEffect(() => { if (draft && draft.text) setText(draft.text); }, [draft && draft.nonce]);

  async function send(message) {
    const msg = (message ?? text).trim();
    if (!msg || sending) return;
    setText(""); setSending(true);
    setMsgs((m) => [...m, { role: "user", content: msg }]);
    try {
      const r = await api.chat(pid, module, msg, pending);
      setMsgs((m) => [...m, { role: "agent", content: r.reply, status: r.status }]);
      setPending(r.status === "needs_info" ? r.pending : null);
      setCur(r.status === "ready" ? r : r.status === "blocked" ? { ...r, changes: [] } : null);
    } catch (e) {
      setMsgs((m) => [...m, { role: "agent", content: e.message, status: "error" }]);
    } finally { setSending(false); }
  }

  async function apply() {
    if (!cur || !cur.changes || !cur.changes.length) return;
    const res = await run((rev) => api.apply(pid, module, cur.changes, rev), null);
    if (res) {
      toast(`${applyLabel} done - revision ${res.context.revision}`, "good");
      setMsgs((m) => [...m, { role: "system", content: `✔ ${applyLabel} applied (revision ${res.context.revision}). Save the module when you're happy with it.` }]);
      setCur(null); setPending(null);
    }
  }
  const cancel = () => { setCur(null); setPending(null); setMsgs((m) => [...m, { role: "system", content: "Cancelled - nothing was changed." }]); };

  const ready = cur && cur.status === "ready" && cur.changes && cur.changes.length;
  return div({ className: "chat" },
    div({ className: "chat-head" }, span({ className: "chat-title" }, title), pending && Badge({ tone: "warn" }, "waiting for your answer")),
    div({ className: "chat-log", "aria-live": "polite" },
      !msgs.length && p({ className: "muted pad" }, "Describe what you want in plain language. Nothing is written until you confirm the preview."),
      msgs.map((m, i) => div({ key: i, className: `msg ${m.role} ${m.status || ""}` }, m.content)),
      sending && div({ className: "msg agent typing" }, "…"),
      div({ ref: endRef })),
    cur && cur.rule_hits && cur.rule_hits.length ? RuleList({ hits: cur.rule_hits }) : null,
    cur && cur.preview ? Preview({ preview: cur.preview, masters }) : null,
    ready ? div({ className: "chat-confirm" }, Btn({ kind: "primary", onClick: apply }, applyLabel), Btn({ onClick: cancel }, "Cancel")) : null,
    chips.length ? div({ className: "chips" }, chips.map((c) => button({ key: c, className: "chip", onClick: () => setText(c) }, c))) : null,
    form({ className: "chat-input", onSubmit: (e) => { e.preventDefault(); send(); } },
      textarea({ value: text, rows: 2, placeholder, "aria-label": title + " message", onChange: (e) => setText(e.target.value),
        onKeyDown: (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } } }),
      Btn({ kind: "primary", type: "submit", busy: sending, disabled: !text.trim() }, "Send")));
}
