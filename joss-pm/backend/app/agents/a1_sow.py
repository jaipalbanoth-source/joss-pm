"""A1 - SOW Intelligence Agent. Non-interactive, JSON in / JSON out, never writes.
Reads the SOW text, proposes all 14 Edit Project header fields (value + confidence + SOW source + evidence),
cross-checks Salesforce and extracts the signals A2 uses.  Rule-based implementation of the design's contract;
swap `run()` for a call to the Glean agent without touching the callers."""
from __future__ import annotations
import difflib
import re
from datetime import date

from ..dates import MONTHS, add_months, find_dates, iso, parse_iso
from .. import context as C

_SENT = re.compile(r"(?<=[.!?])\s+")


def _sentence_around(text: str, pos: int, width: int = 160) -> str:
    a = max(text.rfind("\n", 0, pos), text.rfind(". ", 0, pos))
    b_candidates = [x for x in (text.find("\n", pos), text.find(". ", pos)) if x != -1]
    b = min(b_candidates) if b_candidates else len(text)
    snippet = text[a + 1:b + 1].strip()
    return re.sub(r"\s+", " ", snippet)[:width * 2]


def _section_of(text: str, pos: int) -> str:
    last = None
    for m in re.finditer(r"(?m)^\s*(\d{1,2})\.\s+([A-Z][A-Za-z &/]+)\s*$", text):
        if m.start() <= pos:
            last = m
    return f"SOW §{last.group(1)} {last.group(2).strip()}" if last else "SOW"


def _field(value, conf, text=None, pos=None, evidence=None, source=None):
    if value is None or conf < C.MED:
        return {"value": None, "confidence": round(conf, 2) if value is not None else 0, "source": source, "evidence": evidence, "conflict": None}
    return {"value": value, "confidence": round(conf, 2),
            "source": source or (_section_of(text, pos) if text is not None and pos is not None else "SOW"),
            "evidence": evidence or (_sentence_around(text, pos) if text is not None and pos is not None else None), "conflict": None}


# -------------------------------------------------------------- individual extractors
def _customer(text, customers, sf_account):
    pats = [r"between\s+(.{2,70}?)\s*\(\s*[\"“”']?(?:the\s+)?Client", r"(?im)^\s*(?:Client|Customer)\s*:\s*(.+)$",
            r"(?i)prepared for\s+(.{2,60}?)[\.\n]", r"(?im)^SOW-[\w-]+\s*\|\s*(.+?)\s*/\s*Jade Global"]
    for i, p in enumerate(pats):
        m = re.search(p, text)
        if m:
            raw = m.group(1).strip(" .,\"“”")
            canon = next((c for c in customers if c.casefold() == raw.casefold()), None)
            if not canon:
                close = difflib.get_close_matches(raw, customers, 1, 0.85)
                canon = close[0] if close else None
            ev = _sentence_around(text, m.start())
            if canon:
                return _field(canon, 0.97 if i == 0 else 0.93, text, m.start(), ev)
            if sf_account and raw.casefold() == sf_account.casefold():
                return _field(sf_account, 0.9, text, m.start(), ev)
            return _field(raw, 0.7, text, m.start(), ev)
    return _field(None, 0)


def _title(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines[:6]):
        if re.fullmatch(r"(?i)statement of work|sow|work order", l) and i + 1 < len(lines):
            return lines[i + 1], text.find(lines[i + 1])
    m = re.search(r"(?im)^\s*(?:Project(?: Title| Name)?|Title)\s*:\s*(.+)$", text)
    if m:
        return m.group(1).strip(), m.start()
    return None, None


def _short_name(title: str, customer: str | None) -> str:
    t = re.sub(r"(?i)\b(statement of work|sow)\b[:\-– ]*", "", title).strip(" -–:")
    if customer:
        first = customer.split()[0]
        if not t.lower().startswith(first.lower()):
            t = f"{first} {t}"
    return t[:60]


def _description(text):
    m = re.search(r"(?im)^\s*\d{0,2}\.?\s*(scope of work|project scope|scope|services|description of services)\s*$", text)
    if not m:
        return _field(None, 0)
    body = text[m.end():]
    nxt = re.search(r"(?m)^\s*\d{1,2}\.\s+[A-Z]", body)
    body = body[:nxt.start()] if nxt else body
    body = re.sub(r"\s+", " ", body).strip()
    sents = [s for s in _SENT.split(body) if s]
    summary = " ".join(sents[:3])
    if len(summary) > 480:
        summary = summary[:477].rsplit(" ", 1)[0] + "..."
    return _field(summary, 0.86, text, m.start(), "Drafted from the SOW scope section.", _section_of(text, m.start()))


def _dates(text):
    """Return (start_cell, finish_cell)."""
    starts, ends = [], []
    for m in re.finditer(r"(?i)(commenc\w*|effective(?:\s+date)?|start\s*date|start(?:s|ing)?\b|begin\w*|kick-?off)[^.\n]{0,50}", text):
        for d, a, b in find_dates(m.group(0), date(2000, 1, 1)):
            # require explicit year inside SOW dates; find_dates will also accept partial ones - filter on a 4-digit year
            if re.search(r"\d{4}", m.group(0)[a:b]):
                ev = _sentence_around(text, m.start())
                strong = bool(re.search(r"(?i)commenc|start\s*date|effective", m.group(1)))
                starts.append((d, m.start(), 0.93 if strong else 0.8, ev))
                break
    for m in re.finditer(r"(?i)(end\s*date|ending|ends?\s+on|completion\s*date|expires?\s+on|term\s+ends|until|through)[^.\n]{0,40}", text):
        for d, a, b in find_dates(m.group(0), date(2000, 1, 1)):
            if re.search(r"\d{4}", m.group(0)[a:b]):
                ends.append((d, m.start(), 0.9, _sentence_around(text, m.start())))
                break
    s_cell = f_cell = None
    start = min(starts) if starts else None   # earliest explicit start
    if start:
        s_cell = _field(start[0], start[2], text, start[1], start[3])
    else:  # fall back to the first phase window "Nov 2026 - Dec 2026"
        m = re.search(r"(?i)\b([A-Za-z]{3,9})\s+(\d{4})\s*[-–]\s*[A-Za-z]{3,9}\s+\d{4}", text)
        if m and MONTHS.get(m.group(1).lower()):
            s_cell = _field(date(int(m.group(2)), MONTHS[m.group(1).lower()], 1).isoformat(), 0.65, text, m.start())
    end = max(ends) if ends else None
    if end:
        f_cell = _field(end[0], end[2] if len({e[0] for e in ends}) == 1 else end[2] - 0.03, text, end[1], end[3])
    elif s_cell and s_cell["value"]:
        m = re.search(r"(?i)(?:duration|term|period)\b[^.\n]{0,40}?(\d+)\s*(month|week|day)s?", text)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            sd = parse_iso(s_cell["value"])
            fd = add_months(sd, n) if unit == "month" else sd.fromordinal(sd.toordinal() + n * (7 if unit == "week" else 1))
            fd = fd.fromordinal(fd.toordinal() - 1)
            f_cell = _field(fd.isoformat(), 0.8, text, m.start(), f"{_sentence_around(text, m.start())} (start date + {n} {unit}s)")
    return s_cell or _field(None, 0), f_cell or _field(None, 0)


_MODELS = [  # (regex, model, confidence)
    (r"(?i)on\s+a\s+(fixed[\s-]*price|fixed[\s-]*fee)\s+basis", "Fixed Price", 0.95),
    (r"(?i)on\s+a\s+(time\s*(?:and|&)\s*materials?|t\s*&\s*m)\s+basis", "T&M", 0.95),
    (r"(?i)on\s+a\s+milestone[\s-]*based\s+basis|milestone[\s-]*based\s+(?:fee|billing)", "Milestone", 0.9),
    (r"(?i)\bretainer\b", "Retainer", 0.88),
    (r"(?i)fixed[\s-]*(?:price|fee)", "Fixed Price", 0.88),
    (r"(?i)time\s*(?:and|&)\s*materials?|\bT&M\b", "T&M", 0.88),
    (r"(?i)milestone", "Milestone", 0.7),
]


def _execution_model(text, allowed):
    for pat, model, conf in _MODELS:
        m = re.search(pat, text)
        if m and model in allowed:
            return _field(model, conf, text, m.start())
    return _field(None, 0)


def _po(text):
    for pat, conf in [(r"(?i)Purchase\s+Order\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{3,})", 0.93),
                      (r"(?i)Customer\s+(?:Reference|Project\s*ID)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{3,})", 0.9),
                      (r"\bPO[-\s]?(\d{4,})\b", 0.8)]:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip(".")
            if re.fullmatch(r"(?i)(no|number)", raw):
                continue
            value = raw if pat != r"\bPO[-\s]?(\d{4,})\b" else f"PO-{raw}"
            return _field(value, conf, text, m.start())
    return _field(None, 0)


def _tolerance(text):
    m = re.search(r"(?i)(?:tolerance|variance)[^.\n%]{0,40}?(\d{1,2}(?:\.\d)?)\s*%", text)
    if m:
        return _field(float(m.group(1)), 0.86, text, m.start())
    return _field(None, 0)


# -------------------------------------------------------------- QA signals
_PLATFORMS = [("ERP Cloud", r"oracle fusion|fusion (?:cloud )?(?:financials|erp)|oracle erp|erp cloud|netsuite|sap s/4"),
              ("CRM", r"salesforce|sales cloud|service cloud|dynamics 365 (?:sales|crm)|\bcrm\b"),
              ("Data Platform", r"data platform|lakehouse|snowflake|databricks|data lake|data warehouse"),
              ("HCM", r"\bhcm\b|workday|oracle hcm|human capital"),
              ("Healthcare Apps", r"healthcare app|ehr|epic|cerner|patient"),
              ("ServiceNow", r"servicenow|service now")]
_SCOPES = [("Implementation", r"implement|go-live|go live|deploy|build and configure|rollout"),
           ("Migration", r"migrat|data load"),
           ("Upgrade", r"upgrade|re-?platform|optimi[sz]"),
           ("Support", r"managed (?:support|services)|maintenance|support services|incident"),
           ("Integration", r"integration|interface"),
           ("Testing", r"\btesting\b|qa services|regression")]


def qa_signals(text, title, exec_model, start, finish):
    low = text.lower()
    plats = []
    for name, pat in _PLATFORMS:
        n = len(re.findall(pat, low))
        if n:
            plats.append((n, name))
    plats.sort(reverse=True)
    weights = {}
    for name, pat in _SCOPES:
        n = len(re.findall(pat, low)) + 4 * len(re.findall(pat, (title or "").lower()))
        if name == "Implementation":
            n += 2 * len(re.findall(r"go-live|go live|cutover", low))
        if name in ("Migration", "Integration", "Testing") and n:
            n = max(1, n // 2)          # supporting activities weigh less than the primary service
        if n:
            weights[name] = n
    scope = [k for k, _ in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0] != "Implementation"))]
    if re.search(r"hybrid|agile with a fixed milestone|agile.{0,30}fixed milestone", low):
        delivery = "Hybrid"
    elif (scope and scope[0] == "Support") or len(re.findall(r"\bsla\b|itil|incident", low)) >= 2:
        delivery = "Managed"
    elif re.search(r"waterfall|phase[- ]gate", low):
        delivery = "Waterfall"
    elif re.search(r"agile|scrum|sprint", low):
        delivery = "Agile"
    else:
        delivery = None
    months = None
    if start and finish:
        a, b = parse_iso(start), parse_iso(finish)
        months = round(((b - a).days + 1) / 30.4, 1)
    cycles = re.search(r"(\d+|three|two|four)\s+test cycles?", low)
    return {"platforms": [n for _, n in plats], "scope": scope, "delivery": delivery, "commercial_model": exec_model,
            "testing": {"mentioned": bool(re.search(r"\bsit\b|\buat\b|regression|testing", low)), "cycles": cycles.group(1) if cycles else None},
            "duration_months": months}


# -------------------------------------------------------------- orchestration
def run(payload: dict) -> dict:
    """payload: {project_id, sow_text, sow_filename, opportunity:{...}, customers:[...], exec_models:{...}}"""
    text = payload.get("sow_text") or ""
    opp = payload["opportunity"]
    models = payload["exec_models"]
    warnings, errors = [], []
    out = {"project_id": payload["project_id"], "fields": {}, "qa_signals": None, "warnings": warnings, "errors": errors}
    F = out["fields"]
    if not text.strip():
        errors.append("SOW text is empty or unreadable (scanned PDF?). Upload a text-based SOW or fill the form manually.")
        return out

    F["customer_name"] = _customer(text, payload["customers"], opp["account_name"])
    if F["customer_name"]["value"] and F["customer_name"]["value"].casefold() != opp["account_name"].casefold():
        warnings.append(f"SOW customer '{F['customer_name']['value']}' differs from the Salesforce Account '{opp['account_name']}'.")
    title, tpos = _title(text)
    if title:
        F["project_name"] = _field(_short_name(title, F["customer_name"]["value"]), 0.9, text, tpos, f"SOW title: {title}", "SOW title")
    else:
        F["project_name"] = _field(opp["name"][:60], 0.7, source="Salesforce Opportunity name", evidence=opp["name"])
    F["project_description"] = _description(text)
    s_cell, f_cell = _dates(text)
    F["start_date"], F["finish_date"] = s_cell, f_cell
    for key, sf_key, sf_label in (("start_date", "start_date", "Project_start_date__c"), ("finish_date", "end_date", "Project_end_date__c")):
        c = F[key]
        if c["value"] and opp.get(sf_key) and c["value"] != opp[sf_key]:
            c["conflict"] = {"sow_value": c["value"], "salesforce_value": opp[sf_key], "salesforce_field": sf_label}
            warnings.append(f"{key}: SOW {c['value']} differs from Salesforce {sf_label} {opp[sf_key]}.")
        elif not c["value"] and opp.get(sf_key):
            warnings.append(f"{key} not found in the SOW; Salesforce has {opp[sf_key]} (not used automatically).")
    em = _execution_model(text, models)
    F["execution_model"] = em
    policy = models.get(em["value"]) if em["value"] else None
    F["customer_project_id"] = _po(text)
    tol = _tolerance(text)
    if tol["value"] is not None:
        F["tolerance_pct"] = tol
    elif policy:
        F["tolerance_pct"] = {"value": policy["tolerance_pct"], "confidence": None, "source": f"Policy: {em['value']}",
                              "evidence": "No tolerance clause in the SOW - policy default.", "conflict": None, "origin": "default"}
    else:
        F["tolerance_pct"] = _field(None, 0)
    if policy:
        for k in ("margin_target", "auto_timesheet_submit", "timesheet_approval"):
            F[k] = {"value": policy[k], "confidence": None, "source": f"Policy: {em['value']}", "evidence": "Delivery-unit policy default - PM confirms.",
                    "conflict": None, "origin": "default"}
    else:
        for k in ("margin_target", "auto_timesheet_submit", "timesheet_approval"):
            F[k] = _field(None, 0)
    F["sales_margin"] = {"value": None, "confidence": None, "source": "Resource Mgmt (estimate)", "evidence": "Computed from estimate lines.", "conflict": None, "origin": "linked"}
    F["process_status"] = {"value": "Draft", "confidence": None, "source": "System", "evidence": None, "conflict": None, "origin": "system"}
    F["active_yn"] = {"value": "N", "confidence": None, "source": "System", "evidence": None, "conflict": None, "origin": "system"}
    out["qa_signals"] = qa_signals(text, title, em["value"], F["start_date"]["value"], F["finish_date"]["value"])
    if not F["customer_project_id"]["value"]:
        warnings.append("No PO / customer project ID found in the SOW; the chat will ask the PM for it.")
    return out


def merge_into_context(ctx: dict, a1: dict, keep_pm_edits: bool = True) -> list[str]:
    """Write A1's proposals into the Project Context. PM-edited cells survive a re-run. Returns changed keys."""
    changed = []
    for key, f in a1["fields"].items():
        cur = ctx["edit_project"][key]
        if keep_pm_edits and cur.get("origin") == "pm":
            continue
        origin = f.get("origin", "sow")
        new = C.cell(f.get("value"), f.get("confidence"), f.get("source"), f.get("evidence"), f.get("conflict"), origin)
        if key in ("process_status", "active_yn", "sales_margin"):
            new = C.cell(cur.get("value"), None, f.get("source"), f.get("evidence"), None, origin)
        if (cur.get("value"), cur.get("conflict")) != (new["value"], new["conflict"]):
            changed.append(key)
        ctx["edit_project"][key] = new
    ctx["a1"] = {"qa_signals": a1["qa_signals"], "warnings": a1["warnings"], "errors": a1["errors"]}
    return changed
