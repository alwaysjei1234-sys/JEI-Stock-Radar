"""Export validated whole-market official daily closes for paper simulations."""
import argparse
import json
import math
import re
from pathlib import Path

DEFAULT_INPUT = Path("remote/daily_prices.json")
MIN_QUOTES = 500


def export_archive(daily, day):
    if not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", str(day)):
        raise ValueError("交易日日期格式錯誤")
    if (not isinstance(daily, dict) or daily.get("schema") != 1 or
            daily.get("kind") != "official_daily_close" or
            not isinstance(daily.get("days"), dict)):
        raise ValueError("日價歷史檔不是官方收盤格式")
    source = daily["days"].get(day)
    if not isinstance(source, dict):
        raise ValueError("官方日價歷史檔缺少指定交易日")
    quotes = {}
    for raw_code, raw_price in source.items():
        code = str(raw_code).strip()
        if not re.fullmatch(r"[0-9A-Z]{4,8}", code):
            continue
        if (isinstance(raw_price, bool) or
                not isinstance(raw_price, (int, float)) or
                not math.isfinite(raw_price) or raw_price <= 0):
            continue
        quotes[code] = float(raw_price)
    if len(quotes) < MIN_QUOTES:
        raise ValueError(f"官方收盤價覆蓋不足：{len(quotes)}/{MIN_QUOTES}")
    return {
        "schema": 1,
        "kind": "official_daily_close",
        "data_date": day,
        "source": "remote/daily_prices.json: official daily closes",
        "coverage_count": len(quotes),
        "days": {day: quotes},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    daily = json.loads(args.input.read_text(encoding="utf-8"))
    archive = export_archive(daily, args.day)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create keeps dated official price records immutable.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(archive, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    print(f"Archived {archive['coverage_count']} official closes for {args.day}")


if __name__ == "__main__":
    main()
