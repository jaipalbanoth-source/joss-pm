// REST client for the FastAPI backend. Same origin when served by uvicorn; override with ?api=http://host:8000 for a dev server.
const qs = new URLSearchParams(location.search);
const BASE = (qs.get("api") || "").replace(/\/$/, "");
let user = localStorage.getItem("joss_user") || "jaipal.banoth@jadeglobal.com";

export const getUser = () => user;
export const setUser = (u) => { user = u.trim().toLowerCase(); localStorage.setItem("joss_user", user); };

export class ApiError extends Error {
  constructor(status, message, hits = [], extra = {}) { super(message); this.status = status; this.hits = hits; this.extra = extra; }
}

async function call(method, path, body, isForm = false) {
  const headers = { "X-User-Email": user };
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + "/api" + path, { method, headers, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body) });
  } catch (e) {
    throw new ApiError(0, "Cannot reach the JOSS PM backend. Is it running on port 8000?");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const d = data && data.detail;
    if (d && typeof d === "object" && !Array.isArray(d)) throw new ApiError(res.status, d.message || "Request failed", d.hits || [], d);
    if (Array.isArray(d)) throw new ApiError(res.status, d.map((x) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; "));
    throw new ApiError(res.status, typeof d === "string" ? d : `Request failed (${res.status})`);
  }
  return data;
}

const enc = encodeURIComponent;
export const api = {
  health: () => call("GET", "/health"),
  masters: () => call("GET", "/masters"),
  rules: () => call("GET", "/rules"),
  opportunities: () => call("GET", "/opportunities"),
  dashboard: () => call("GET", "/dashboard"),
  audit: (pid, limit = 200) => call("GET", `/audit?limit=${limit}` + (pid ? `&project_id=${enc(pid)}` : "")),
  projects: () => call("GET", "/projects"),
  createProject: (opportunity_id) => call("POST", "/projects", { opportunity_id }),
  project: (pid) => call("GET", `/projects/${enc(pid)}`),
  deleteProject: (pid) => call("DELETE", `/projects/${enc(pid)}`),
  sow: (pid) => call("GET", `/projects/${enc(pid)}/sow`),
  replaceSow: (pid, text, filename, keep_pm_edits) => call("POST", `/projects/${enc(pid)}/sow`, { text, filename, keep_pm_edits }),
  uploadSow: (pid, file) => { const f = new FormData(); f.append("file", file); return call("POST", `/projects/${enc(pid)}/sow/upload`, f, true); },
  rerunA1: (pid, keep_pm_edits) => call("POST", `/projects/${enc(pid)}/a1/run`, { keep_pm_edits }),
  editProject: (pid, body) => call("PUT", `/projects/${enc(pid)}/edit-project`, body),
  setQa: (pid, body) => call("PUT", `/projects/${enc(pid)}/qa`, body),
  saveModule: (pid, module, expected_revision) => call("POST", `/projects/${enc(pid)}/modules/${module}/save`, { expected_revision }),
  chat: (pid, module, message, pending, structured) => call("POST", `/projects/${enc(pid)}/chat/${module}`, { message, pending: pending || null, structured: structured || null }),
  chatHistory: (pid, module) => call("GET", `/projects/${enc(pid)}/chat/${module}`),
  apply: (pid, module, changes, expected_revision) => call("POST", `/projects/${enc(pid)}/apply/${module}`, { changes, expected_revision }),
  pkg: (pid) => call("GET", `/projects/${enc(pid)}/package`),
  submit: (pid, body) => call("POST", `/projects/${enc(pid)}/submit`, body),
  setStatus: (pid, status) => call("POST", `/projects/${enc(pid)}/status`, { status }),
  setDelegates: (pid, delegates) => call("PUT", `/projects/${enc(pid)}/delegates`, { delegates }),
  simulateHours: (pid, tid, hours) => call("POST", `/projects/${enc(pid)}/tasks/${enc(tid)}/simulate-hours`, { hours }),
  revisions: (pid) => call("GET", `/projects/${enc(pid)}/revisions`),
  revision: (pid, rev) => call("GET", `/projects/${enc(pid)}/revisions/${rev}`),
  qaOverrides: (pid) => call("GET", `/projects/${enc(pid)}/qa-overrides`),
  joss: (pid) => call("GET", `/projects/${enc(pid)}/joss`),
};
