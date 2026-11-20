"""A2 - QA Classifier Agent. Scores every combination in the QA master against the SOW signals and returns the top 3.
Only combinations that exist in the master can be suggested (the agent cannot invent one)."""
from __future__ import annotations

WEIGHTS = {"platform": 0.30, "type": 0.30, "delivery": 0.20, "commercial": 0.20}
THRESHOLD = 0.70   # pre-select when best score >= threshold (tune in UAT)


def run(payload: dict) -> dict:
    """payload: {project_id, qa_signals, execution_model:{value,confidence}, qa_master:[...]}"""
    sig = payload.get("qa_signals") or {}
    em = payload.get("execution_model") or {}
    unknown, warnings = [], []
    platforms = sig.get("platforms") or []
    scope = sig.get("scope") or []
    delivery = sig.get("delivery")
    commercial = sig.get("commercial_model")
    if not commercial and em.get("value") and (em.get("confidence") or 0) >= 0.60:
        commercial = em["value"]
    if not platforms:
        unknown.append("platform")
    if not scope:
        unknown.append("type")
    if not delivery:
        unknown.append("delivery")
    if not commercial:
        unknown.append("commercial")

    scored = []
    for q in payload["qa_master"]:
        parts, reasons = {}, []
        if platforms and q["platform"] in platforms:
            parts["platform"] = 1.0 if platforms[0] == q["platform"] else 0.7
            reasons.append(f"SOW names {q['platform']}")
        if scope and q["type"] in scope:
            parts["type"] = 1.0 if scope[0] == q["type"] else 0.4
            reasons.append(f"scope is {q['type'].lower()}" + ("" if scope[0] == q["type"] else " (secondary)"))
        if delivery and q["delivery"] == delivery:
            parts["delivery"] = 1.0
            reasons.append(f"{delivery} delivery approach")
        if commercial and q["commercial"] == commercial:
            parts["commercial"] = 1.0
            reasons.append(f"{commercial} commercial model")
        score = round(sum(WEIGHTS[k] * parts.get(k, 0) for k in WEIGHTS), 2)
        if score > 0:
            scored.append({"combination_id": q["combination_id"], "label": q["label"], "score": score, "reasons": reasons, "parts": parts})
    scored.sort(key=lambda x: (-x["score"], -len(x["reasons"]), x["combination_id"]))
    top = scored[:3]
    best = top[0]["score"] if top else 0
    pre = top[0]["combination_id"] if top and best >= THRESHOLD else None
    if not top:
        warnings.append("No usable signals in the SOW; pick a combination manually.")
    elif pre is None:
        warnings.append(f"Best score {best} is below the {THRESHOLD} threshold; nothing pre-selected.")
    return {"project_id": payload.get("project_id"), "preselect": pre, "selected_combination_id": pre, "best_score": best,
            "threshold": THRESHOLD, "top3": top, "signals_used": {"platforms": platforms, "scope": scope, "delivery": delivery,
                                                                   "commercial": commercial, "unknown_parts": unknown},
            "warnings": warnings, "errors": []}


def chat(message: str, qa_master: list, current: str | None) -> dict:
    """Tiny chat helper for the QA tab: 'use QA-105' or 'choose ERP Cloud migration hybrid'."""
    import re
    m = re.search(r"QA-\d{3}", message, re.I)
    if m:
        cid = m.group(0).upper()
        hit = next((q for q in qa_master if q["combination_id"] == cid), None)
        if hit:
            return {"status": "ready", "combination_id": cid, "reply": f"Select {cid}: {hit['label']}?"}
        return {"status": "blocked", "reply": f"{cid} does not exist in the QA master (QA-01)."}
    words = [w for w in re.findall(r"[a-z&]+", message.lower()) if w not in ("use", "choose", "select", "pick", "the", "a", "qa", "set", "to", "as")]
    if not words:
        return {"status": "needs_info", "reply": "Tell me the combination (e.g. 'use QA-105' or 'ERP Cloud migration hybrid')."}
    cands = []
    for q in qa_master:
        hay = q["label"].lower().replace("&", "&")
        if all(w in hay for w in words):
            cands.append(q)
    if len(cands) == 1:
        return {"status": "ready", "combination_id": cands[0]["combination_id"], "reply": f"Select {cands[0]['combination_id']}: {cands[0]['label']}?"}
    if not cands:
        return {"status": "blocked", "reply": "No combination in the QA master matches that. Only master combinations can be selected (QA-01)."}
    return {"status": "needs_info", "reply": "Several combinations match - which one?\n" + "\n".join(f"{i}. {c['combination_id']} {c['label']}" for i, c in enumerate(cands[:6], 1))}
