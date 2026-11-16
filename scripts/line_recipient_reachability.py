"""Safely verify bot-recipient profile reachability without sending or reading PII.

LINE HTTP 200 push acceptance is NOT proof of actual handset delivery.
Profile GET status 200 means the configured bot can access the target user;
404 means not reachable (invalid/not friend/blocked/no profile consent).
Never read, log, publish, or persist the profile body, token or user ID.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from scripts.send_line_brief import TAIPEI

PROFILE_BASE = "https://api.line.me/v2/bot/profile/"


def check_reachability(token, user_id, opener=urllib.request.urlopen):
    if not token or not re.fullmatch(r"U[0-9a-f]{32}", user_id or ""):
        return "credentials_unconfigured"
    req = urllib.request.Request(PROFILE_BASE + user_id, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    }, method="GET")
    try:
        with opener(req, timeout=10) as response:
            # Never read the profile body; status is sufficient for diagnostics.
            if response.status == 200:
                return "profile_accessible"
            return "unexpected_http_status"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "profile_not_accessible"
        if exc.code in (401, 403):
            return "channel_auth_denied"
        if exc.code == 429:
            return "rate_limited"
        return "other_http_error"
    except (OSError, TimeoutError, ValueError):
        return "network_unverified"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    status = check_reachability(
        os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN", ""),
        os.getenv("JEI_LINE_USER_ID", ""),
    )
    doc = {
        "schema": 1,
        "checked_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "status": status,
        "profile_delivery_proven": False,
        "handset_notification_confirmed": False,
        "method": "LINE Messaging API profile HTTP status only; body never read",
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print("LINE bot-to-recipient profile reachability:", status)
    # Profile 404 and misconfiguration are diagnostics, not proof of delivery;
    # give a CI-visible signal without printing or serializing private values.
    if status not in ("profile_accessible",):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
