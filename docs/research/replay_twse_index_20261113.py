"""Replay dated official TAIEX snapshots. No alerts are sent."""
import hashlib
import json
from datetime import time
from pathlib import Path
from urllib.request import urlopen


def replay(day, raw):
    doc = json.loads(raw)
    assert doc["stat"] == "OK" and doc["date"] == day
    assert doc["fields"][:2] == ["時間", "發行量加權股價指數"]
    rows = [(time.fromisoformat(r[0]), float(r[1].replace(",", ""))) for r in doc["data"]]
    assert len(rows) == 3241
    seconds = [t.hour * 3600 + t.minute * 60 + t.second for t, _ in rows]
    assert seconds == list(range(9 * 3600, 13 * 3600 + 30 * 60 + 1, 5))
    ref = rows[0][1]
    ticks = rows[1:-1]
    grid = [(t, p) for t, p in ticks if t.minute % 5 == 0 and t.second == 0]
    def first(samples, floor):
        return next((t.isoformat() for t, p in samples if 100 * (p / ref - 1) <= floor), None)
    return {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(rows),
        "reference_close": ref,
        "close": rows[-1][1],
        "intraday_low": min(p for _, p in ticks),
        "thresholds": {str(floor): {"first_official_5s": first(ticks, floor),
                                    "first_5m_sample": first(grid, floor)}
                       for floor in (-2.0, -2.5)},
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    report = {}
    for day in ("20261112", "20261113"):
        url = f"https://www.twse.com.tw/exchangeReport/MI_5MINS_INDEX?date={day}&response=json"
        if args.fixtures:
            raw = (args.fixtures / f"jei21-index-{day}.json").read_bytes()
        else:
            with urlopen(url, timeout=20) as response:
                raw = response.read()
        report[day] = {"url": url, **replay(day, raw)}
    print(json.dumps(report, indent=2))
