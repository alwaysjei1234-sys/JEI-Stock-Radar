"""Read-only TWSE/TPEx feed quality guard. Standard library only."""
import datetime as dt
import json
import urllib.request

SOURCES = {
    "TWSE": ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "Code", "Date", "ClosingPrice"),
    "TPEX": ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "SecuritiesCompanyCode", "Date", "Close"),
}

def parse_date(value):
    s = str(value).strip().replace("/", "").replace("-", "")
    if len(s) == 7 and s.isdigit():
        return dt.date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7])).isoformat()
    if len(s) == 8 and s.isdigit():
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat()
    raise ValueError("invalid date: " + str(value))

def validate(rows, code_key, date_key, close_key):
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty feed")
    seen, dates = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get(code_key, "")).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        try:
            date = parse_date(row.get(date_key))
            close = float(str(row.get(close_key, "")).replace(",", ""))
            if close <= 0:
                continue
        except (ValueError, TypeError):
            continue
        seen.add((date, code))
        dates.add(date)
    if not seen:
        raise ValueError("no valid quotes")
    if len(dates) != 1:
        raise ValueError("mixed dates: " + repr(sorted(dates)))
    return {"date": next(iter(dates)), "valid_stocks": len(seen), "raw_rows": len(rows)}

def run():
    report = {"checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "ok", "sources": {}}
    for name, (url, code, date, close) in SOURCES.items():
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "JEI-FeedGuard/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                rows = json.load(response)
            report["sources"][name] = validate(rows, code, date, close)
        except Exception as exc:
            report["sources"][name] = {"error": str(exc)}
            report["status"] = "failed"
    if report["status"] == "ok" and report["sources"]["TWSE"]["date"] != report["sources"]["TPEX"]["date"]:
        report["status"] = "date_mismatch"
    return report

if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "ok" else 1)
