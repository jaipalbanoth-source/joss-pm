from datetime import date, datetime, timezone
import os


def today() -> date:
    o = os.environ.get("JOSS_TODAY")
    return date.fromisoformat(o) if o else date.today()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
