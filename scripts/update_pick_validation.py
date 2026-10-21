#!/usr/bin/env python3
"""JEI forward-only stock-pick validation, independent of broker fills and private holdings.

Each vetted daily close freezes that day's top picks. Day 3/7/15/20/30/40/60
means *future archived trading closes*, not calendar days. A missing horizon
is pending, not a loss, win or a guessed exit. No automatic parameter tuning.
"""
import json
import math
import re
import statistics
from scripts.pick_risk_metrics import max_close_drawdown, duplicate_signal_summary
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "remote/system.json"
DAILY = ROOT / "remote/daily_prices.json"
PICKS = ROOT / "remote/pick_history.json"
REPORT = ROOT / "remote/pick_validation.json"
TZ = ZoneInfo("Asia/Taipei")
GROUPS = ("attack", "next", "monster", "tomorrow_monster", "future_monster")
HORIZONS = (3, 7, 15, 20, 30, 40, 60)
FEE = 0.001425
SELL_TAX = 0.003
MAX_PICKS = 5


def quote(quotes, code):
    try:
        p = float(quotes.get(code, 0))
        return p if math.isfinite(p) and p > 0 else None
    except (ValueError, TypeError, AttributeError):
        return None


def close_verified(feed, archive, date):
    """Strict same-date official close. Never use a quote fetched on the next day."""
    if not isinstance(feed, dict) or not isinstance(archive, dict):
        return False
    market = feed.get("market") or {}
    if not isinstance(market, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        return False
    count = market.get("close_count")
    if (feed.get("data_date") != date or market.get("mode") != "今日收盤"
            or market.get("stale") is not False or isinstance(count, bool)
            or not isinstance(count, (int, float)) or count < 500):
        return False
    if feed.get("holdings") not in (None, {}):
        return False
    try:
        stamp = datetime.strptime(feed["updated_at"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        if stamp.date().isoformat() != date or stamp.hour*60+stamp.minute < 810:
            return False
    except (KeyError, ValueError, TypeError):
        return False
    if archive.get("schema") != 1 or archive.get("kind") != "official_daily_close":
        return False
    days = archive.get("days")
    prices = days.get(date) if isinstance(days, dict) else None
    return isinstance(prices, dict) and sum(quote(prices, x) is not None for x in prices) >= 500


def freeze_picks(feed, prices, date, origin="scheduled_close"):
    """Records exactly the historical top-five ordering; no hindsight or repricing."""
    frozen = []
    for group in GROUPS:
        seen = set()
        source = feed.get(group) or []
        if not isinstance(source, list):
            continue
        for original_rank, row in enumerate(source, 1):
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            if not re.fullmatch(r"\d{4}", code) or code in seen:
                continue
            price = quote(prices, code)
            try:
                shown = float(row.get("price"))
                score = float(row.get("score"))
            except (TypeError, ValueError):
                continue
            # The recorded recommendation must agree with the official archive.
            if (price is None or not math.isfinite(shown) or not math.isfinite(score)
                    or shown <= 0 or abs(shown / price - 1) > 0.005):
                continue
            seen.add(code)
            frozen.append({
                "id": f"{date}:{group}:{code}", "day": date, "group": group,
                "rank": original_rank, "code": code,
                "name": str(row.get("name") or code)[:40],
                "score": round(score, 2),
                "signal_close": price, "origin": origin
            })
            if len(seen) >= MAX_PICKS:
                break
    return frozen


def net_percent(start, finish):
    # Estimated round-trip friction, NOT a claim of executable close fill.
    return 100 * (finish*(1-FEE-SELL_TAX) / (start*(1+FEE)) - 1)


def compile_report(frozen, archive, updated_at):
    days_data = archive["days"]
    days = sorted(k for k,v in days_data.items()
                  if isinstance(k,str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}",k)
                  and isinstance(v,dict)
                  and sum(quote(v,c) is not None for c in v)>=500)
    observed = []
    for p in frozen:
        if p["day"] not in days:
            continue
        first = quote(days_data[p["day"]], p["code"])
        if first is None or abs(first/p["signal_close"]-1) > 0.005:
            continue
        origin_idx = days.index(p["day"])
        progression = []
        # Keep the completed horizons separate; do not include signals without exits.
        for horizon in HORIZONS:
            final_idx = origin_idx+horizon
            if final_idx >= len(days):
                progression.append({"trading_days":horizon, "status":"pending"})
                continue
            last_day = days[final_idx]
            last_price = quote(days_data[last_day],p["code"])
            if last_price is None:
                progression.append({"trading_days":horizon, "status":"missing_price",
                                    "end_day":last_day})
                continue
            closes = [quote(days_data[d],p["code"]) for d in days[origin_idx+1:final_idx+1]]
            close_returns = [(c/first-1)*100 for c in closes if c is not None]
            if len(close_returns) != horizon:
                progression.append({"trading_days":horizon, "status":"missing_price",
                                    "end_day":last_day,
                                    "observed_closes":len(close_returns),
                                    "expected_closes":horizon})
                continue
            progression.append({
                "trading_days":horizon, "status":"complete", "end_day":last_day,
                "end_close":last_price, "gross_return_pct":round((last_price/first-1)*100,3),
                "estimated_net_return_pct":round(net_percent(first,last_price),3),
                "best_close_return_pct":round(max(close_returns),3) if close_returns else None,
                "worst_close_return_pct":round(min(close_returns),3) if close_returns else None,
                "max_close_drawdown_pct":max_close_drawdown(first, closes),
                "observed_closes":sum(c is not None for c in closes),
                "expected_closes":horizon
            })
        latest = None
        for d in reversed(days[origin_idx+1:]):
            end = quote(days_data[d],p["code"])
            if end is not None:
                latest={"day":d,"price":end,"gross_return_pct":round((end/first-1)*100,3)}
                break
        observed.append({**p, "outcomes":progression, "latest_observation":latest})
    groups = {}
    for group in GROUPS:
        groups[group] = {}
        for horizon in HORIZONS:
            results = [r for p in observed if p["group"] == group
                       for r in p["outcomes"]
                       if r["trading_days"]==horizon and r["status"]=="complete"]
            values = [r["estimated_net_return_pct"] for r in results]
            m = len(values)
            groups[group][str(horizon)] = {
                "completed":m,
                "pending":sum(1 for p in observed if p["group"]==group
                              for r in p["outcomes"] if r["trading_days"]==horizon
                              and r["status"]=="pending"),
                "missing_price":sum(1 for p in observed if p["group"]==group
                                    for r in p["outcomes"] if r["trading_days"]==horizon
                                    and r["status"]=="missing_price"),
                "win_rate_pct":round(100*sum(v>0 for v in values)/m,2) if m else None,
                "avg_estimated_net_pct":round(statistics.mean(values),3) if m else None,
                "median_estimated_net_pct":round(statistics.median(values),3) if m else None,
                "best_estimated_net_pct":round(max(values),3) if m else None,
                "worst_estimated_net_pct":round(min(values),3) if m else None,
                "worst_max_close_drawdown_pct":round(min(r["max_close_drawdown_pct"] for r in results),3) if m else None,
            }
    return {
        "schema":1, "mode":"forward_official_close_pick_validation",
        "updated_at":updated_at, "latest_official_day":days[-1] if days else None,
        "horizons_trading_days":list(HORIZONS), "groups":groups, "picks":observed,
        "duplicate_signal_summary":duplicate_signal_summary(observed),
        "total_frozen_picks":len(frozen),
        "analysis_notes":[
            "每個交易日的主攻／下一棒／妖股／明日妖股／未來妖股取當時前五檔，當日官方收盤價封存；不得事後換股或補選贏家。",
            "3、7、15、20、30、40、60 為後續交易日數（20日約1個月、40日約2個月、60日約3個月），未到期一律 pending。",
            "假設訊號日收盤買入、指定未來收盤賣出，只是股價觀察；無法保證當時能成交。估算買賣兩端手續費及賣出交易稅；不含滑價、最低手續費。",
            "不同分類可能包含相同股票，不能把類別績效當成獨立投資組合；未成熟或缺價樣本不能算勝負。",
            "僅以事前保存名單與日後已驗證官方收盤計分。有效樣本不足時不選最佳策略、不自動修改參數。"
        ],
        "estimated_costs":{"buy_fee":FEE,"sell_fee":FEE,"sell_tax":SELL_TAX,
                           "slippage_included":False}
    }


def update(feed, archive, prior, now):
    """Return updated immutable historical picks and report without network activity."""
    if not isinstance(prior,dict) or prior.get("schema")!=1 or not isinstance(prior.get("picks"),list):
        raise ValueError("選股封存帳本格式錯誤，不可覆寫")
    days=archive.get("days") if isinstance(archive,dict) else None
    if not isinstance(days,dict) or archive.get("kind")!="official_daily_close":
        raise ValueError("官方每日收盤封存不可用")
    local=now.astimezone(TZ)
    today=local.date().isoformat()
    asof=str(feed.get("data_date") or "")
    stored=list(prior["picks"])
    # Historical signals are append-only: reject corrupt or duplicated identities.
    ids=set()
    for pick in stored:
        if not isinstance(pick,dict):
            raise ValueError("封存推薦資料格式錯誤，不可覆寫")
        identity=pick.get("id")
        expected=f"{pick.get('day')}:{pick.get('group')}:{pick.get('code')}"
        if not isinstance(identity,str) or identity!=expected or identity in ids:
            raise ValueError("封存推薦識別碼錯誤或重複，不可覆寫")
        ids.add(identity)
    captured=False
    origin="scheduled_close"
    # The very first import may seed the latest *audited* Friday close on a
    # weekend; never manufacture prior multi-day historical picks.
    bootstrap=(not stored and asof in days and asof==max(days)
               and 0 <= (local.date()-datetime.strptime(asof,"%Y-%m-%d").date()).days <= 7
               if re.fullmatch(r"\d{4}-\d{2}-\d{2}",asof) else False)
    if asof==today or bootstrap:
        stamp = None
        try:
            stamp = datetime.strptime(str(feed.get("updated_at") or ""),
                                      "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        except (ValueError, TypeError):
            pass
        # Prevent a future-dated feed from being captured before the session.
        if (stamp is not None and stamp <= local and
                close_verified(feed,archive,asof)):
            if not any(x.get("day")==asof for x in stored):
                origin="verified_archive_bootstrap" if bootstrap and asof!=today else origin
                new=freeze_picks(feed,days[asof],asof,origin)
                if not new:
                    raise ValueError("已驗證行情但沒有可封存的選股名單")
                stored.extend(new)
                captured=True
    # Even without a fresh feed, all previously sealed picks get their horizons
    # recomputed from verified official close archives.
    report=compile_report(stored,archive,local.strftime("%Y-%m-%d %H:%M"))
    if len(report["picks"])!=len(stored):
        raise ValueError("封存推薦無法完整核對官方歷史收盤價，拒絕產生不完整績效")
    return {"schema":1,"mode":"immutable_asof_pick_archive","picks":stored},report,captured


def main():
    now=datetime.now(TZ)
    feed=json.loads(FEED.read_text(encoding="utf-8"))
    archive=json.loads(DAILY.read_text(encoding="utf-8"))
    prior=json.loads(PICKS.read_text(encoding="utf-8")) if PICKS.exists() else {
        "schema":1,"mode":"immutable_asof_pick_archive","picks":[]}
    ledger,report,captured=update(feed,archive,prior,now)
    if captured or not PICKS.exists():
        PICKS.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Refresh when the schema or risk fields change, even on a non-trading day.
    if (captured or not REPORT.exists() or
            any(json.loads(REPORT.read_text(encoding="utf-8")).get(key) != report.get(key)
                for key in ("latest_official_day", "duplicate_signal_summary", "groups")) or
            "max_close_drawdown_pct" not in REPORT.read_text(encoding="utf-8")):
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"captured":captured,"latest_official_day":report["latest_official_day"],
                      "picks":len(ledger["picks"]),
                      "completed_3day":sum(1 for p in report["picks"]
                              for x in p["outcomes"] if x["trading_days"]==3 and x["status"]=="complete")},
                     ensure_ascii=False))


if __name__=="__main__":
    main()
