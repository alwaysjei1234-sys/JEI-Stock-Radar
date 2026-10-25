#!/usr/bin/env python3
"""Build a public, attributed Taiwan research snapshot from free official APIs.

No credentials are needed. The file contains public company/market data only;
it must never be used for a user's private holdings or transaction records.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request
from http.client import IncompleteRead
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"
SOURCES = {
    "twseRevenue": f"{TWSE}/opendata/t187ap05_L",
    "twseMargin": f"{TWSE}/exchangeReport/MI_MARGN",
    "twseValuation": f"{TWSE}/exchangeReport/BWIBBU_ALL",
    "twseIncome": f"{TWSE}/opendata/t187ap06_L_ci",
    "twseBalance": f"{TWSE}/opendata/t187ap07_L_ci",
    "tpexRevenue": f"{TPEX}/mopsfin_t187ap05_O",
    "tpexMargin": f"{TPEX}/tpex_mainboard_margin_balance",
    "tpexSbl": f"{TPEX}/tpex_margin_sbl",
    "tpexIncome": f"{TPEX}/mopsfin_t187ap06_O_ci",
    "tpexBalance": f"{TPEX}/mopsfin_t187ap07_O_ci",
}


def fetch_json(url: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "JEI-Stock-Radar/1.0 (free public market research)"})
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))
            if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
                raise ValueError(f"Unexpected public API payload: {url}")
            return payload
        except (urllib.error.URLError, TimeoutError, IncompleteRead, json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Official free API unavailable after 3 attempts: {url}: {last_error}") from last_error


def roc_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) != 7 or not text.isdigit():
        return None
    try:
        return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:])).isoformat()
    except ValueError:
        return None


def number(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() in ("", "-", "--"):
            return None
        result = float(str(value).replace(",", "").replace("%", ""))
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def revenue_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        code = str(row.get("公司代號", "")).strip().upper()
        if not code:
            continue
        result[code] = {
            "name": row.get("公司名稱"),
            "period": roc_date(str(row.get("資料年月", "")) + "01"),
            "publishedAt": roc_date(row.get("出表日期")),
            "monthlyRevenue": number(row.get("營業收入-當月營收")),
            "monthlyYoYPct": number(row.get("營業收入-去年同月增減(%)")),
            "monthlyMoMPct": number(row.get("營業收入-上月比較增減(%)")),
            "cumulativeRevenue": number(row.get("累計營業收入-當月累計營收")),
            "cumulativeYoYPct": number(row.get("累計營業收入-前期比較增減(%)")),
        }
    return result


def twse_margin_rows(rows: list[dict[str, Any]], market_date: str | None) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        code = str(row.get("股票代號", "")).strip().upper()
        if not code:
            continue
        buy = number(row.get("融資今日餘額"))
        buy_prev = number(row.get("融資前日餘額"))
        short = number(row.get("融券今日餘額"))
        quota = number(row.get("融資限額"))
        result[code] = {
            "name": row.get("股票名稱"), "marketDate": market_date,
            "marginBuyBalance": buy,
            "marginBuyChange": buy - buy_prev if buy is not None and buy_prev is not None else None,
            "marginShortBalance": short,
            "marginUsagePct": round(buy / quota * 100, 4) if buy is not None and quota else None,
        }
    return result


def tpex_margin_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        code = str(row.get("SecuritiesCompanyCode", "")).strip().upper()
        if not code:
            continue
        buy = number(row.get("MarginPurchaseBalance"))
        previous = number(row.get("MarginPurchaseBalancePreviousDay"))
        quota = number(row.get("MarginPurchaseQuota"))
        result[code] = {
            "name": row.get("CompanyName"), "marketDate": roc_date(row.get("Date")),
            "marginBuyBalance": buy,
            "marginBuyChange": buy - previous if buy is not None and previous is not None else None,
            "marginShortBalance": number(row.get("ShortSaleBalance")),
            "marginUsagePct": number(row.get("MarginPurchaseUtilizationRate"))
            if row.get("MarginPurchaseUtilizationRate") not in (None, "")
            else (round(buy / quota * 100, 4) if buy is not None and quota else None),
        }
    return result


def tpex_sbl_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        code = str(row.get("SecuritiesCompanyCode", "")).strip().upper()
        if code:
            result[code] = {
                "marketDate": roc_date(row.get("Date")),
                "sblShortBalance": number(row.get("SecuritiesBorrowingBalanceOfTheMarketDay")),
                "marginShortSaleBalance": number(row.get("SaleBalanceOfTheMarketDay")),
            }
    return result


def valuation_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        code = str(row.get("Code", "")).strip().upper()
        if code:
            result[code] = {
                "marketDate": roc_date(row.get("Date")),
                "pe": number(row.get("PEratio")),
                "dividendYieldPct": number(row.get("DividendYield")),
                "pb": number(row.get("PBratio")),
            }
    return result


def financial_rows(income_rows: list[dict[str, Any]], balance_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Normalize the latest same-company, same-quarter income/balance rows only."""
    def get(row: dict[str, Any], *keys: str) -> Any:
        return next((row.get(key) for key in keys if row.get(key) not in (None, "")), None)

    def period(row: dict[str, Any]) -> tuple[int, int] | None:
        year = get(row, "年度", "Year")
        season = get(row, "季別", "Season")
        try:
            year_number = int(str(year))
            year_number = year_number + 1911 if year_number < 1911 else year_number
            quarter = int(str(season))
        except (TypeError, ValueError):
            return None
        return (year_number, quarter) if 1 <= quarter <= 4 else None

    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, tuple[int, int]], dict[str, Any]]:
        result = {}
        for row in rows:
            code = str(get(row, "公司代號", "SecuritiesCompanyCode") or "").strip().upper()
            key = period(row)
            if not code or key is None:
                continue
            identity = (code, key)
            previous = result.get(identity)
            current_date = roc_date(get(row, "出表日期", "Date")) or ""
            previous_date = roc_date(get(previous, "出表日期", "Date")) if previous else None
            if previous is None or current_date >= (previous_date or ""):
                result[identity] = row
        return result

    income_by_period = index(income_rows)
    balance_by_period = index(balance_rows)
    latest_period_by_code = {}
    for code, key in set(income_by_period) | set(balance_by_period):
        if key > latest_period_by_code.get(code, (0, 0)):
            latest_period_by_code[code] = key

    result = {}
    for code, key in latest_period_by_code.items():
        income = income_by_period.get((code, key), {})
        balance = balance_by_period.get((code, key), {})
        revenue = number(get(income, "營業收入", "OperatingRevenue"))
        gross = number(get(income, "營業毛利（毛損）淨額", "營業毛利（毛損）", "GrossProfit"))
        operating = number(get(income, "營業利益（損失）", "OperatingIncome"))
        net = number(get(income, "淨利（淨損）歸屬於母公司業主", "本期淨利（淨損）", "NetIncome"))
        assets = number(get(balance, "資產總計", "TotalAssets"))
        liabilities = number(get(balance, "負債總計", "TotalLiabilities"))
        current_assets = number(get(balance, "流動資產", "CurrentAssets"))
        current_liabilities = number(get(balance, "流動負債", "CurrentLiabilities"))
        year_label, season = key
        dates = [roc_date(get(row, "出表日期", "Date")) for row in (income, balance)]
        dates = [value for value in dates if value]
        result[code] = {
            "industryCoverage": "general_industry",
            "period": f"{year_label}-Q{season}",
            "publishedAt": max(dates) if dates else None,
            "grossMarginPct": round(gross / revenue * 100, 4) if gross is not None and revenue else None,
            "operatingMarginPct": round(operating / revenue * 100, 4) if operating is not None and revenue else None,
            "parentNetMarginPct": round(net / revenue * 100, 4) if net is not None and revenue else None,
            "eps": number(get(income, "基本每股盈餘（元）", "基本每股盈餘", "EPS")),
            "debtRatioPct": round(liabilities / assets * 100, 4) if liabilities is not None and assets else None,
            "currentRatioPct": round(current_assets / current_liabilities * 100, 4) if current_assets is not None and current_liabilities else None,
            "bookValuePerShare": number(get(balance, "每股參考淨值", "BookValuePerShare")),
        }
    return result


def load_market_date(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("data_date")
        return value if isinstance(value, str) and len(value) == 10 else None
    except (OSError, ValueError, AttributeError):
        return None


def build_snapshot(api: Any, market_date: str | None, generated_at: str | None = None) -> dict[str, Any]:
    twse_revenue = api(SOURCES["twseRevenue"])
    tpex_revenue = api(SOURCES["tpexRevenue"])
    twse_margin = api(SOURCES["twseMargin"])
    tpex_margin = api(SOURCES["tpexMargin"])
    valuation = api(SOURCES["twseValuation"])
    tpex_sbl = api(SOURCES["tpexSbl"])
    twse_income = api(SOURCES["twseIncome"])
    twse_balance = api(SOURCES["twseBalance"])
    tpex_income = api(SOURCES["tpexIncome"])
    tpex_balance = api(SOURCES["tpexBalance"])
    twse = {code: {"revenue": value} for code, value in revenue_rows(twse_revenue).items()}
    otc = {code: {"revenue": value} for code, value in revenue_rows(tpex_revenue).items()}
    twse_margin_map = twse_margin_rows(twse_margin, market_date)
    otc_margin_map = tpex_margin_rows(tpex_margin)
    for code, value in twse_margin_map.items():
        twse.setdefault(code, {"name": value["name"]}).update({"margin": value})
    for code, value in otc_margin_map.items():
        otc.setdefault(code, {"name": value["name"]}).update({"margin": value})
    for code, value in valuation_rows(valuation).items():
        twse.setdefault(code, {}).update({"valuation": value})
    for code, value in financial_rows(twse_income, twse_balance).items():
        twse.setdefault(code, {}).update({"financials": value})
    for code, value in financial_rows(tpex_income, tpex_balance).items():
        otc.setdefault(code, {}).update({"financials": value})
    for code, value in tpex_sbl_rows(tpex_sbl).items():
        otc.setdefault(code, {}).setdefault("margin", {}).update(value)
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "marketDate": market_date,
        "license": "Official free public APIs; attribution/source links retained. Verify source terms before reuse.",
        "sources": SOURCES,
        "markets": {"listed": twse, "otc": otc},
    }


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    output = root / "remote" / "free_research.json"
    system_path = root / "remote" / "system.json"
    snapshot = build_snapshot(fetch_json, load_market_date(system_path))
    write_atomic(output, snapshot)
    print(f"Wrote {output}: TWSE={len(snapshot['markets']['listed'])}, TPEx={len(snapshot['markets']['otc'])}, market_date={snapshot['marketDate']}")
