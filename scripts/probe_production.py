#!/usr/bin/env python3
"""Check public JEI endpoints and the known-invalid AI token rejection path.

Does not use user credentials, private portfolios, real model prompts or paid AI.
This check deliberately exits nonzero for Vercel login/protection pages.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "https://jei-stock-radar.vercel.app"
REPORT = "/tmp/jei_public_health.json"
USER_AGENT = "JEI-Production-Health/1.1"


def request(path, *, method="GET", body=None, headers=None):
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status, response.read(1000000).decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(65536).decode("utf-8", "replace"), "HTTP " + str(exc.code)
    except Exception as exc:
        return None, "", type(exc).__name__


def parse_json(raw):
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def classify(code, body, reason):
    if code in (401, 403) and any(
        marker in body.lower() for marker in
        ("vercel authentication", "deployment protection", "vercel security checkpoint", "log in to vercel")
    ):
        return "VERCEL_LOGIN_PROTECTION"
    if code in (401, 403):
        return "AUTH_OR_ACCESS_BLOCK"
    if code is None:
        return reason or "NETWORK_ERROR"
    if code != 200:
        return reason or "HTTP_" + str(code)
    return "UNEXPECTED_RESPONSE"


def health_ai(data):
    return (
        isinstance(data, dict)
        and data.get("service") == "JEI Free Multi-AI"
        and data.get("free_only") is True
        and data.get("paid_gateway") is False
        and data.get("tokenRequired") is True
        and isinstance(data.get("providers"), dict)
        and isinstance(data["providers"].get("groq_oss"), dict)
    )


def health_manifest(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("versionCode"), int)
        and data["versionCode"] >= 34
        and str(data.get("url", "")).startswith(
            "https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/releases/download/jei-latest/"
        )
    )


CASES = [
    ("/api/consult", "AI Health", health_ai),
    ("/remote/system.json", "Market Feed", lambda x: isinstance(x, dict) and "market" in x and "data_date" in x),
    ("/remote/index.html", "Home UI", lambda x: isinstance(x, str) and "JEI_REMOTE_UI_V3" in x),
    ("/remote/update.json", "Android Update", health_manifest),
    ("/index.html", "Home Link", lambda x: isinstance(x, str) and "<html" in x.lower()),
    ("/strategy.html", "Strategy Page", lambda x: isinstance(x, str) and "<html" in x.lower()),
    ("/industry_research.html", "Industry Research Page", lambda x: isinstance(x, str) and "<html" in x.lower()),
    ("/cash.html", "Performance Page", lambda x: isinstance(x, str) and "<html" in x.lower()),
    ("/holding-health.html", "Holdings Page", lambda x: isinstance(x, str) and "<html" in x.lower()),
    ("/pick_validation.html", "Pick Validation Page", lambda x: isinstance(x, str) and "<html" in x.lower()),
]


def main():
    results = []
    for path, label, check in CASES:
        status, raw, reason = request(path)
        content = raw if path.endswith(".html") else parse_json(raw)
        ok = status == 200 and check(content)
        why = "" if ok else classify(status, raw, reason)
        results.append({
            "endpoint": label, "path": path, "http": status,
            "available": ok, "reason": why,
        })
        print(label + ":", "OK" if ok else "BLOCKED_OR_INVALID", status, why, flush=True)

    # Wrong token is rejected by the JEI application itself, not merely by
    # Vercel authentication. No AI provider should receive this request.
    auth_status, raw, reason = request(
        "/api/consult",
        method="POST",
        body=b'{"question":"JEI health probe - intentionally invalid token"}',
        headers={
            "Content-Type": "application/json",
            "X-JEI-Token": "JEI-INTENTIONALLY-INVALID-HEALTH-PROBE",
        },
    )
    reply = parse_json(raw)
    denied = (
        auth_status == 401
        and isinstance(reply, dict)
        and reply.get("error") == "JEI 私人連線碼不正確"
    )
    why = "" if denied else classify(auth_status, raw, reason)
    if not denied and why == "AUTH_OR_ACCESS_BLOCK":
        why = "NOT_JEI_APPLICATION_401"
    results.append({
        "endpoint": "AI Token Authorization", "path": "/api/consult POST",
        "http": auth_status, "available": denied, "reason": why,
    })
    print("AI Token Authorization:", "JEI_401_CONFIRMED" if denied else "BLOCKED_OR_INVALID",
          auth_status, why, flush=True)

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Only anonymous GET and invalid-token denial check; no paid AI calls or user data.")
    if not all(r["available"] for r in results):
        print("FAIL: production cannot be declared publicly reachable.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
