import { createContext, useContext, useState, useEffect, useCallback, useRef } from "../vendor/react.js";
import { api, ApiError } from "./api.js";
import { useToast } from "./components/ui.js";

export const MastersCtx = createContext(null);
export const useMasters = () => useContext(MastersCtx);
export const nameOf = (masters, id) => (masters?.associates || []).find((a) => a.associate_id === id)?.name || id || "-";

/** Loads a project view and exposes guarded mutations (busy flag, optimistic-concurrency + error toasts). */
export function useProject(pid) {
  const toast = useToast();
  const [view, setView] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const pidRef = useRef(pid);
  pidRef.current = pid;

  const reload = useCallback(async () => {
    try { const v = await api.project(pidRef.current); setView(v); setError(null); return v; }
    catch (e) { setError(e); return null; }
  }, []);
  useEffect(() => { setView(null); setError(null); reload(); }, [pid, reload]);

  /** run(fn(rev)) -> new view (or {view}) ; errors become toasts. Returns the result or null. */
  const run = useCallback(async (fn, okMsg) => {
    setBusy(true);
    try {
      const rev = view?.context?.revision;
      const res = await fn(rev);
      const v = res && res.context ? res : res && res.view ? res.view : null;
      if (v) setView(v);
      if (okMsg) toast(okMsg, "good");
      return res;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && /revision|changed|out-of-date/i.test(e.message)) {
        toast("This project changed elsewhere - reloaded the latest version. Please re-check and retry.", "bad");
        reload();
      } else toast(e.message || String(e), "bad");
      return null;
    } finally { setBusy(false); }
  }, [view, toast, reload]);

  return { view, setView, error, busy, reload, run };
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    return fn().then((data) => setState({ loading: false, data, error: null }), (error) => setState({ loading: false, data: null, error }));
  }, deps); // eslint-disable-line
  useEffect(() => { reload(); }, [reload]);
  return { ...state, reload };
}

export function useHashRoute() {
  const [hash, setHash] = useState(location.hash || "#/");
  useEffect(() => {
    const f = () => setHash(location.hash || "#/");
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return hash.replace(/^#/, "") || "/";
}
export const go = (path) => { location.hash = "#" + path; };
