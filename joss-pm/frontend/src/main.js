import { createRoot, useState, useEffect } from "../vendor/react.js";
import { h, ce, div, span, input, button, header, main, nav, a } from "./h.js";
import { api, getUser, setUser } from "./api.js";
import { ToastProvider, Spinner, ErrorBox, Btn } from "./components/ui.js";
import { MastersCtx, useHashRoute, go } from "./state.js";
import { Dashboard } from "./pages/Dashboard.js";
import { Workspace } from "./pages/Workspace.js";

function Shell({ children }) {
  const [user, setU] = useState(getUser());
  return div({ className: "shell" },
    header({ className: "topbar" },
      button({ className: "brand", onClick: () => go("/") }, span({ className: "logo" }, "J"), "JOSS Project Management"),
      div({ className: "who" }, span({ className: "muted" }, "Signed in as "),
        input({ className: "who-in", value: user, "aria-label": "Your email", onChange: (e) => setU(e.target.value), onBlur: () => { if (user.includes("@")) setUser(user); else setU(getUser()); },
          onKeyDown: (e) => e.key === "Enter" && e.target.blur() }))),
    main({ className: "content" }, children));
}

function App() {
  const route = useHashRoute();
  const [masters, setMasters] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => api.masters().then(setMasters, setErr);
  useEffect(() => { load(); }, []);
  const m = /^\/p\/([^/]+)(?:\/([^/]+))?/.exec(route);
  let body;
  if (err) body = div({ className: "page" }, ErrorBox({ error: err, onRetry: () => { setErr(null); load(); } }));
  else if (!masters) body = div({ className: "page" }, Spinner({ label: "Connecting to the JOSS PM backend…" }));
  else body = m ? ce(Workspace, { key: m[1], pid: decodeURIComponent(m[1]), tab: m[2] || "edit_project" }) : ce(Dashboard, null);
  return ce(ToastProvider, null, ce(MastersCtx.Provider, { value: masters }, ce(Shell, null, body)));
}

createRoot(document.getElementById("root")).render(ce(App, null));
