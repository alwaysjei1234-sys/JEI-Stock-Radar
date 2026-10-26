"""Dated TWSE/TPEx closure exceptions; never infer an open session from weekday alone.

This calendar supplements (never replaces) official exchange-date/quote checks.
Unscheduled closures must be added only after a verified exchange announcement.
"""
from datetime import date, timedelta

SCHEDULED_2026 = {
    "2026-01-01": "元旦",
    "2026-02-12": "春節封關後結算日",
    "2026-02-13": "春節封關後結算日",
    **{f"2026-02-{day:02d}": "農曆春節" for day in range(16, 21)},
    "2026-02-27": "和平紀念日補假",
    **{f"2026-04-{day:02d}": "兒童節／清明節" for day in range(3, 7)},
    "2026-05-01": "勞動節",
    "2026-06-19": "端午節",
    "2026-09-25": "中秋節",
    "2026-09-28": "教師節",
    "2026-10-09": "國慶日補假",
    "2026-10-26": "光復節補假",
    "2026-12-25": "行憲紀念日",
}
UNSCHEDULED = {
    "2026-10-23": "薔琵颱風：證交所公告集中市場全日休市",
}

def closure_reason(day):
    """Return a confirmed scheduled/exception closure reason, or None."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    if day.weekday() >= 5:
        return "週末例假日"
    key = day.isoformat()
    return UNSCHEDULED.get(key) or SCHEDULED_2026.get(key)

def next_expected_session(day):
    """Next scheduled weekday; unexpected future closures remain possible."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    for delta in range(1, 16):
        candidate = day + timedelta(days=delta)
        if closure_reason(candidate) is None:
            return candidate.isoformat()
    return None
