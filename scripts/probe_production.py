#!/usr/bin/env python3
"""Anonymous GET-only production reachability check; never sends secrets."""
import json
import urllib.error
import urllib.request

BASE = "https://jei-stock-radar.vercel.app"
CASES = [
    ("/api/consult", "AI", lambda raw: isinstance(raw, dict) and raw.get("service") == "JEI Free Multi-AI"),
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
with open("/tmp/jei_public_health.json", "w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)
print("Probe is GET-only, no secrets, no provider calls, no paid AI usage.")
