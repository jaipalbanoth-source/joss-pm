import { createContext, useContext, useState, useCallback, useEffect, useRef } from "../../vendor/react.js";
import { h, div, span, button, h3, p, ce } from "../h.js";

// ---------------------------------------------------------------- toasts
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((msg, tone = "info") => {
    const id = Math.random();
    setItems((x) => [...x, { id, msg, tone }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), tone === "bad" ? 7000 : 3500);
  }, []);
  return ce(ToastCtx.Provider, { value: push }, children,
    div({ className: "toasts", role: "status", "aria-live": "polite" },
      items.map((i) => div({ key: i.id, className: "toast " + i.tone }, i.msg))));
}

// ---------------------------------------------------------------- primitives
export const Btn = ({ kind = "default", busy, disabled, children, ...rest }) =>
  button({ className: `btn ${kind}`, disabled: disabled || busy, ...rest }, busy ? span({ className: "spin" }) : null, children);

export const Badge = ({ tone = "neutral", title, children }) => span({ className: `badge ${tone}`, title }, children);
export const Card = ({ title, actions, children, className = "" }) =>
  div({ className: "card " + className },
    (title || actions) && div({ className: "card-head" }, h3(title), div({ className: "card-actions" }, actions)),
    div({ className: "card-body" }, children));
export const Empty = ({ children }) => div({ className: "empty" }, children);
export const Spinner = ({ label = "Loading…" }) => div({ className: "loading" }, span({ className: "spin" }), label);
export const ErrorBox = ({ error, onRetry }) =>
  div({ className: "banner bad" }, p(error?.message || String(error)), onRetry && Btn({ onClick: onRetry }, "Retry"));

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return div({ className: "modal-bg", onMouseDown: (e) => e.target === e.currentTarget && onClose() },
    div({ className: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": title },
      div({ className: "modal-head" }, h3(title), button({ className: "icon-btn", onClick: onClose, "aria-label": "Close" }, "×")),
      div({ className: "modal-body" }, children)));
}

export function Tabs({ tabs, active, onChange }) {
  return div({ className: "tabs", role: "tablist" }, tabs.map((t) =>
    button({ key: t.key, role: "tab", "aria-selected": active === t.key, className: "tab" + (active === t.key ? " active" : ""), onClick: () => onChange(t.key) },
      t.label, t.badge)));
}

// ---------------------------------------------------------------- rule hits
export function RuleList({ hits, compact }) {
  if (!hits || !hits.length) return null;
  return div({ className: "rules" }, hits.map((r, i) =>
    div({ key: i, className: "rule " + (r.level === "BLOCK" ? "bad" : "warn") },
      span({ className: "rule-id" }, r.id || r.rule), span({ className: "rule-lvl" }, r.level === "BLOCK" ? "Blocks" : "Warning"),
      span({ className: "rule-msg" }, r.message))));
}

export function useBusy() {
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  const run = useCallback(async (fn) => {
    setBusy(true);
    try { return await fn(); } finally { if (alive.current) setBusy(false); }
  }, []);
  return [busy, run];
}

export const confTone = (c) => (c === null || c === undefined ? "neutral" : c >= 0.85 ? "good" : c >= 0.6 ? "warn" : "bad");
export const STATE_META = {
  high: ["good", "High confidence"], default: ["info", "Policy default"], system: ["neutral", "System"], review: ["warn", "Review"],
  missing: ["bad", "Missing"], confirmed: ["good", "Confirmed by PM"], conflict: ["bad", "SOW / Salesforce conflict"],
};
export const STATUS_TONE = { Draft: "neutral", "Ready to Submit": "info", Active: "good", "On Hold": "warn", Closed: "neutral" };
