"""A6 - Commit & Validation Agent. The ONLY writer. Re-runs every rule (never trusting client totals), checks X-01 / X-04,
writes each module to JOSS in dependency order (header -> QA -> contacts -> resources -> tasks - X-05) and returns one result JSON."""
from __future__ import annotations

from .. import context as C
from .. import rules
from ..joss_writer import WriteError

ORDER = ["project", "qa", "contacts", "resources", "tasks"]


def _result(package, overall, modules, warnings, errors):
    return {"submission_id": package["submission_id"], "revision": package["revision"], "overall_status": overall,
            "modules": modules, "warnings": warnings, "errors": errors}


def _all(status):
    return {m: {"status": status} for m in ORDER}


def can_submit(ctx, refs, submitter_email, owner_email, delegates) -> bool:
    """X-04: only the project's current PM, the project owner or a delegate."""
    email = (submitter_email or "").lower()
    pm = C.current_holder(ctx, "Project Manager")
    pm_email = refs["directory"].get(pm["associate_id"], {}).get("email", "") if pm else ""
    allowed = {pm_email.lower(), (owner_email or "").lower()} | {d.lower() for d in delegates or []}
    return bool(email) and email in allowed - {""}


def run(package: dict, refs: dict, writer, *, current_revision: int, submitter: str, owner: str, delegates: list, prior: dict | None) -> dict:
    ctx = C.clone(package["context"])
    if prior and prior["status"] == "success":
        res = prior["result"]
        res = {**res, "idempotent_replay": True}
        return res
    if package["revision"] != current_revision:
        return _result(package, "failed", _all("skipped"), [],
                       [{"rule": "X-01", "module": "submit", "message": f"Out-of-date revision {package['revision']} (current is {current_revision}). Reload and submit again."}])
    if not can_submit(ctx, refs, submitter, owner, delegates):
        return _result(package, "failed", _all("skipped"), [],
                       [{"rule": "X-04", "module": "submit", "message": f"{submitter or 'Unknown user'} is not the project's PM, owner or a delegate."}])
    C.recompute(ctx, refs)
    hits = rules.validate(ctx, refs, scope="submit")
    errors = [{"rule": h["id"], "module": h["module"], "ref": h["ref"], "message": h["message"]} for h in hits if h["level"] == "BLOCK"]
    warnings = [{"rule": h["id"], "module": h["module"], "ref": h["ref"], "message": h["message"]} for h in hits if h["level"] == "WARN"]
    if errors:
        return _result(package, "failed", _all("skipped"), warnings, errors)

    modules = _all("skipped")
    for m in ORDER:
        try:
            modules[m] = getattr(writer, m)(ctx)
        except WriteError as e:
            modules[m] = {"status": "failed", "error": str(e)}
            return _result(package, "failed", modules, warnings, [{"rule": "WRITE", "module": m, "message": str(e) + " Retry with the same submission_id; no duplicates will be created."}])
    writer.finalize(ctx)
    return _result(package, "success", modules, warnings, [])
