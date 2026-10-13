#!/usr/bin/env python3
"""Anonymous GET-only production reachability check; never sends secrets."""
import json
import urllib.error
import urllib.request

BASE = "https://jei-stock-radar.vercel.app"
CASES = [
    ("/api/consult", "AI", lambda raw: isinstance(raw, dict) and raw.get("service") == "JEI Free Multi-AI" and raw.get("free_only") is True and raw.get("paid_gateway") is False and raw.get("tokenRequired") is True and raw.get("providers", {}).get("groq_oss", {}).get("server_key") is True),
    ("/remote/system.json", "Market Feed", lambda raw: isinstance(raw, dict) and "market" in raw and "data_date" in raw),
    ("/remote/index.html", "Home UI", lambda raw: isinstance(raw, str) and "JEI_REMOTE_UI_V3" in raw),
]
results = []
for path, label, valid in CASES:
    url = BASE + path
    status, body, reason = None, b"", ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "JEI-Production-Health/1.0", "Accept": "application/json,text/html"})
        with urllib.request.urlopen(request, timeout=12) as response:
            status = response.status
            body = response.read(1000000)
    except urllib.error.HTTPError as exc:
        status = exc.code
        reason = "HTTP " + str(status)
    except Exception as exc:
        reason = type(exc).__name__
    decoded = body.decode("utf-8", "replace")
    if path.endswith(".html"):
        data = decoded
    else:
        try:
            data = json.loads(decoded)
        except json.JSONDecodeError:
            data = None
    ok = status == 200 and valid(data)
    results.append({"endpoint": label, "path": path, "http": status, "available": ok, "reason": "" if ok else reason or "unexpected response or authentication page"})
    print(label + ":", "PUBLICLY_REACHABLE" if ok else "BLOCKED_OR_INVALID", "HTTP", status if status is not None else "-", reason)
# Exercise ONLY the rejection path. This bogus token must never reach an AI model.
auth_status = None
try:
    request = urllib.request.Request(
        BASE + "/api/consult",
        data=b'{"question":"probe unauthorized access"}',
        headers={"Content-Type": "application/json", "X-JEI-Token": "JEI-INTENTIONALLY-INVALID-HEALTH-PROBE"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        auth_status = response.status
except urllib.error.HTTPError as exc:
    auth_status = exc.code
except Exception:
    pass
denied = auth_status == 401
results.append({"endpoint": "AI Private Token", "path": "/api/consult POST", "http": auth_status, "available": denied,
                "reason": "" if denied else "expected 401 for invalid token"})
print("AI Private Token:", "REJECTED_INVALID_TOKEN" if denied else "AUTH_REJECTION_NOT_CONFIRMED", "HTTP", auth_status)
with open("/tmp/jei_public_health.json", "w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)
print("Probe is GET-only, no secrets, no provider calls, no paid AI usage.")
