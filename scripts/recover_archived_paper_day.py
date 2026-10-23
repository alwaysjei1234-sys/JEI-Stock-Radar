"""Safely replay consecutive immutable public paper-signal snapshots after a missed run."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from scripts.update_paper_performance import advance
except ModuleNotFoundError as exc:
    if exc.name not in ("scripts", "scripts.update_paper_performance"):
        raise
    from update_paper_performance import advance

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "remote/strategy_performance.json"
SNAPSHOT_DIR = ROOT / "data/pick_snapshots"
CLOSE_DIR = ROOT / "data/feed_closes"
TZ = ZoneInfo("Asia/Taipei")


def load_close_history(directory=CLOSE_DIR):
    days = {}
    for path in sorted(Path(directory).glob("????-??-??.json")):
        archive = json.loads(path.read_text(encoding="utf-8"))
        if (archive.get("schema") != 1 or archive.get("kind") != "official_daily_close"
                or not isinstance(archive.get("days"), dict)):
            raise ValueError(f"official close archive format invalid: {path}")
        if archive.get("data_date") not in (None, path.stem):
            raise ValueError(f"official close archive date mismatch: {path}")
        quotes = archive["days"].get(path.stem)
        if not isinstance(quotes, dict):
            raise ValueError(f"official close archive missing its dated prices: {path}")
        if path.stem in days and days[path.stem] != quotes:
            raise ValueError(f"conflicting official close archives: {path.stem}")
        days[path.stem] = quotes
    return {"schema": 1, "kind": "official_daily_close", "days": days}


def archived_feed(snapshot, archive):
    day = snapshot.get("data_date")
    captured_at = snapshot.get("captured_at")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
        raise ValueError("archived signal date invalid")
    try:
        captured = datetime.strptime(str(captured_at), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except (TypeError, ValueError) as exc:
        raise ValueError("archived signal capture time missing or invalid") from exc
    if captured.date().isoformat() != day or captured.hour * 60 + captured.minute < 810:
        raise ValueError("archived signal was not captured after same-day close")
    quotes = archive.get("days", {}).get(day)
    if not isinstance(quotes, dict):
        raise ValueError("no official close archive for the signal date")
    coverage = sum(
        isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0
        for price in quotes.values()
    )
    if coverage < 500:
        raise ValueError("official close archive coverage below 500")

    feed = {
        "data_date": day,
        "updated_at": captured_at,
        "market": {"mode": "今日收盤", "stale": False, "close_count": coverage},
        "attack": [],
        "monster": [],
    }
    picks = snapshot.get("picks")
    if not isinstance(picks, list):
        raise ValueError("archived signal picks invalid")
    for pick in picks:
        if not isinstance(pick, dict) or pick.get("as_of") != day:
            raise ValueError("archived pick date mismatch")
        cohort = pick.get("cohort")
        target = {"momentum": "attack", "monster": "monster"}.get(cohort)
        if target is None:
            continue
        item = {"code": str(pick.get("code") or ""), "name": str(pick.get("name") or "")}
        score = pick.get("signal_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            item["score"] = score
        feed[target].append(item)
    return feed


def recover_pending(state, snapshot_dir=SNAPSHOT_DIR, close_dir=CLOSE_DIR):
    last = state.get("last_processed_day")
    if not last:
        return 0
    archive = load_close_history(close_dir)
    recovered = 0
    for path in sorted(Path(snapshot_dir).glob("????-??-??.json")):
        if path.stem <= last:
            continue
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("data_date") != path.stem:
            raise ValueError(f"signal snapshot date mismatch: {path}")
        if path.stem not in archive["days"]:
            break
        feed = archived_feed(snapshot, archive)
        advance(feed, archive, state, path.stem)
        recovered += 1
    return recovered


def main():
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    count = recover_pending(state)
    if count:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Recovered {count} consecutive archived paper day(s); last={state['last_processed_day']}")
    else:
        print("No consecutive archived paper day is pending")


if __name__ == "__main__":
    main()
