"""Price-only strategy observations from dated official-close history.

No intraday feed, fabricated volume, forward prices, or trade execution.
All indicators use only closes available on/as of the signal date.
"""
import math
import statistics

STRATEGY_NAMES = {
    "breakout": "20日收盤突破",
    "bollinger": "布林上軌突破",
    "vcp": "VCP價格收斂觀察",
    "sector": "族群連動",
}

def _range_ratio(values):
    avg = sum(values) / len(values)
    return (max(values) - min(values)) / avg if avg > 0 else math.inf

def attach_verified_ohlcv(patterns, files_by_code):
    """Attach genuine unadjusted TWSE candles only when they match official closes."""
    for rows in patterns.get("signals", {}).values():
        for signal in rows:
            code=str(signal.get("code",""))
            sources=files_by_code.get(code,[])
            if not sources:continue
            candles={}
            valid=True
            for source in sources:
                if (source.get("code")!=code or source.get("market")!="TWSE"
                    or source.get("adjusted_for_corporate_actions") is not False
                    or source.get("ohlcv_units",{}).get("volume")!="shares"):
                    valid=False;break
                for candle in source.get("ohlcv",[]):
                    try:
                        day=candle["date"]
                        o,h,l,c=[float(candle[k]) for k in ("open","high","low","close")]
                        v=candle["volume"]
                        if (not all(math.isfinite(x) and x>0 for x in (o,h,l,c))
                            or not isinstance(v,int) or isinstance(v,bool) or v<0
                            or l>min(o,c) or h<max(o,c) or day in candles):
                            raise ValueError("invalid candle")
                        candles[day]={"date":day,"open":o,"high":h,"low":l,"close":c,"volume":v}
                    except (KeyError,TypeError,ValueError):
                        valid=False;break
                if not valid:break
            series=signal.get("close_series",[])
            if (not valid or len(series)<10 or any(p["date"] not in candles for p in series)
                or any(abs(candles[p["date"]]["close"]-float(p["close"]))>0.0001 for p in series)):
                continue
            ordered=[candles[p["date"]] for p in series]
            signal["ohlcv"]=ordered
            if len(ordered)>=21:
                prior=ordered[-21:-1]
                last=ordered[-1]
                avg_volume=sum(c["volume"] for c in prior)/len(prior)
                prior_high=max(c["high"] for c in prior)
                ratio=(last["volume"]/avg_volume) if avg_volume>0 else None
                breakout=last["close"]>prior_high
                signal["volume_price_observation"]={
                    "basis":"20筆官方原始日K線；未還原除權息；非買賣建議",
                    "prior_20_high":round(prior_high,4),
                    "prior_20_avg_volume_shares":round(avg_volume,2),
                    "latest_volume_shares":last["volume"],
                    "volume_ratio":round(ratio,2) if ratio is not None else None,
                    "price_breakout":breakout,
                    "volume_expansion":ratio is not None and ratio>=1.5,
                    "confirmed_price_volume_breakout":breakout and ratio is not None and ratio>=1.5,
                }
            signal["ohlcv_source_verified"]=True
            signal["ohlcv_adjusted_for_corporate_actions"]=False
    return patterns

def build_pattern_signals(history, by_code, stock_sectors, sectors, asof=None):
    """Produce auditable watchlists; 21 *consecutive snapshot* closes required."""
    out = {
        "schema": 1,
        "data_date": asof or (history[-1].get("date") if history else ""),
        "basis": "官方歷史收盤價；無逐日量能、日內高低價與完整財報驗證",
        "status": "insufficient",
        "history_sessions": len(history),
        "signals": {key: [] for key in STRATEGY_NAMES},
        "names": STRATEGY_NAMES,
    }
    if len(history) < 21:
        return out
    last = history[-1]
    if asof and last.get("date") != asof:
        out["status"] = "date_mismatch"
        return out
    snapshots = history[-21:]
    if len({x.get("date") for x in snapshots}) != 21:
        return out
    for snap in snapshots:
        if not isinstance(snap.get("prices"), dict):
            return out
    score_by_sector = {str(x.get("name", "")): float(x.get("score", 0)) for x in sectors}
    breadth_by_sector = {str(x.get("name", "")): float(x.get("breadth", 0)) for x in sectors}
    included = 0
    for code, stock in by_code.items():
        code = str(code)
        if not (len(code) == 4 and code.isdigit()):
            continue
        closes = [snap["prices"].get(code) for snap in snapshots]
        try:
            closes = [float(p) for p in closes]
        except (ValueError, TypeError):
            continue
        if len(closes) != 21 or not all(math.isfinite(p) and p > 0 for p in closes):
            continue
        included += 1
        prior, price = closes[:-1], closes[-1]
        mean = statistics.fmean(prior)
        sd = statistics.pstdev(prior)
        change = (price / prior[-1] - 1) * 100
        sector = stock_sectors.get(code, "其他")
        heat = score_by_sector.get(sector, 50)
        breadth = breadth_by_sector.get(sector, 50)
        base = {
            "code": code, "name": str(stock.get("name", code)),
            "price": round(price, 4), "change_pct": round(change, 2),
            "sector": sector, "data_date": out["data_date"],
            "basis_sessions": 21,
            "close_series": [{"date": snap["date"], "close": round(value, 4)}
                             for snap, value in zip(snapshots, closes)],
            "reference_levels": {
                "prior_20_close_high": round(max(prior), 4),
                "prior_20_close_low": round(min(prior), 4),
                "prior_20_close_mean": round(mean, 4),
                "basis": "前20筆官方收盤價；非日內高低點、委託進場價或停損價",
            },
        }
        def add(key, strength, description):
            # Relative rank within a given strategy, not success probability.
            score = int(round(max(0, min(99, 50 + strength + max(-12, min(12, (heat - 50) * .15))))))
            out["signals"][key].append({**base, "score": score, "reason": description})
        if price > max(prior) and change > 0:
            gap = (price / max(prior) - 1) * 100
            add("breakout", min(33, gap * 8 + 8), f"收盤突破前20日收盤高點 {max(prior):.2f}；突破 {gap:.2f}%｜未驗證成交量")
        upper = mean + 2 * sd
        if sd > 0 and price > upper and prior[-1] <= upper and change > 0:
            add("bollinger", min(33, (price / upper - 1) * 18 + 11),
                f"收盤 {price:.2f} > 前20日布林上軌 {upper:.2f}｜使用收盤價、非盤中突破")
        wide = _range_ratio(prior[-15:-10])
        medium = _range_ratio(prior[-10:-5])
        tight = _range_ratio(prior[-5:])
        if wide > medium * 1.08 and medium > tight * 1.08 and tight <= .08 and price > mean:
            add("vcp", min(30, (wide - tight) * 120 + 8),
                f"5日波幅 {tight*100:.1f}% < 前期 {medium*100:.1f}% < 更早 {wide*100:.1f}%｜僅價格近似，缺量能確認")
        if heat >= 65 and breadth >= 55 and price > mean and change > 0:
            add("sector", min(35, (heat - 60) * .7 + min(10, change)),
                f"{sector} 熱度 {heat:.0f}｜上漲比 {breadth:.0f}%｜收盤高於20日均價")
    for key in out["signals"]:
        out["signals"][key].sort(key=lambda x: (-x["score"], -x["change_pct"], x["code"]))
        out["signals"][key] = out["signals"][key][:12]
    out["status"] = "ready" if included >= 300 else "coverage_insufficient"
    out["coverage"] = included
    if out["status"] != "ready":
        out["signals"] = {key: [] for key in STRATEGY_NAMES}
    return out
