"""Deterministic, read-only risk alert decision logic for JEI feed."""
import datetime as dt
import json
import sys

def evaluate(feed, previous=None):
    """Return an alert payload or None. No network calls or message delivery."""
    risk = feed.get("risk") or {}
    level = str(risk.get("level", "")).lower()
    score = risk.get("score")
    data_date = feed.get("data_date") or risk.get("as_of")
    if level not in ("red", "orange") or not isinstance(score, (int, float)) or not data_date:
        return None
    dt.date.fromisoformat(data_date)
    fingerprint = f"{data_date}:{level}:{score}"
    if previous == fingerprint:
        return None
    reasons = risk.get("reasons") or []
    return {
        "fingerprint": fingerprint,
        "level": level,
        "score": score,
        "data_date": data_date,
        "text": f"JEI 市場風險警報｜{data_date}｜{level.upper()} {score}/100\n" +
                "\n".join(str(r) for r in reasons[:5]),
        "delivery_status": "not_sent",
    }

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as file:
        feed = json.load(file)
    print(json.dumps(evaluate(feed), ensure_ascii=False, indent=2))
