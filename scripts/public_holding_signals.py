"""Public ticker-only technical signals. No portfolio costs, quantities or P/L.

Signals are computed from dated official closes; missing symbols retain an
explicitly dated, allowlisted prior public signal, never an invented quote.
"""
import re

FIELDS = {"score", "trend", "action", "defense", "target", "reason", "as_of", "status"}
CODE_RE = re.compile(r"(?:[0-9]{4}|[0-9]{5}[A-Z])\Z")

def is_safe_public_holdings(rows):
    if rows is None:
        return True
    if not isinstance(rows, dict):
        return False
    for code, row in rows.items():
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            return False
        if not isinstance(row, dict) or not set(row).issubset(FIELDS):
            return False
        if "score" in row and (isinstance(row["score"], bool) or not isinstance(row["score"], int) or not 0 <= row["score"] <= 100):
            return False
        for key in ("defense", "target"):
            if key in row and row[key] is not None and (isinstance(row[key], bool) or not isinstance(row[key], (int, float)) or not 0 < row[key] < 1000000):
                return False
        for key in ("trend", "action", "reason", "as_of", "status"):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 200):
                return False
    return True

def build_public_holding_signals(previous, price_days, as_of, risk_score, current_closes=None):
    """Update only explicitly listed public tickers from observed dated closes."""
    if not is_safe_public_holdings(previous):
        raise ValueError("Public holdings contain disallowed private fields")
    previous = previous or {}
    if not isinstance(price_days, dict):
        price_days = {}
    current_closes = current_closes or {}
    result = {}
    for code, prior in previous.items():
        observed = []
        for day in sorted(price_days):
            if day > as_of:
                continue
            price = (price_days.get(day) or {}).get(code)
            if isinstance(price, (int, float)) and not isinstance(price, bool) and 0 < price < 1000000:
                observed.append((day, float(price)))
        today_price = current_closes.get(code)
        if isinstance(today_price, (int, float)) and not isinstance(today_price, bool) and 0 < today_price < 1000000:
            if observed and observed[-1][0] == as_of:
                observed[-1] = (as_of, float(today_price))
            else:
                observed.append((as_of, float(today_price)))
        if len(observed) < 5:
            result[code] = dict(prior)
            continue
        prices = [p for _, p in observed]
        close = prices[-1]
        ma5 = sum(prices[-5:]) / 5
        ret5 = (close / prices[-6] - 1) * 100 if len(prices) >= 6 else 0
        ret_all = (close / prices[max(0, len(prices)-8)] - 1) * 100
        clamp = lambda x, lo, hi: max(lo, min(hi, x))
        score = round(clamp(50 + (12 if close >= ma5 else -12)
                            + clamp(ret5 * 1.5, -15, 15)
                            + clamp(ret_all * .7, -8, 8)
                            - (10 if risk_score >= 80 else 0), 10, 90))
        trend = "短線轉強" if close >= ma5 and ret5 > 2 else ("短線偏弱" if close < ma5 and ret5 < 0 else "整理")
        action = "防守觀察" if risk_score >= 80 else ("減碼評估" if trend == "短線偏弱" else "續抱觀察")
        result[code] = {
            "score": score, "trend": trend, "action": action,
            "defense": round(min(prices[-5:]) * .99, 2),
            "target": round(max(prices[-8:]) * 1.02, 2),
            "reason": f"{observed[-1][0]}已驗證收盤；近{min(len(prices),8)}交易日技術面；財報與籌碼未驗證，防守/目標為歷史價位參考",
            "as_of": observed[-1][0], "status": "歷史參考"
        }
    return result
