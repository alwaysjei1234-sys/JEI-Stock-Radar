"""Research-only technical candidate. Inputs are chronological daily OHLCV, no trades."""
import math

def ema(values, span):
    alpha = 2 / (span + 1)
    result = []
    for x in values:
        result.append(x if not result else alpha * x + (1-alpha) * result[-1])
    return result

def rsi(values, period=14):
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]
    if len(changes) < period:
        return [None] * len(values)
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    output = [None] * period
    def value():
        return 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    output.append(value())
    for g, l in zip(gains[period:], losses[period:]):
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        output.append(value())
    return output

def signal(close):
    """Uses only data through the latest completed bar; no backtest success claim."""
    if len(close) < 65 or any(not math.isfinite(float(v)) or float(v) <= 0 for v in close):
        raise ValueError("need_65_valid_positive_closes")
    close = list(map(float, close))
    fast, slow = ema(close, 12), ema(close, 26)
    macd = [a-b for a,b in zip(fast, slow)]
    sig = ema(macd, 9)
    hist = [a-b for a,b in zip(macd, sig)]
    def bb_width(end):
        window = close[end-19:end+1]
        mean = sum(window)/20
        return 4 * math.sqrt(sum((v-mean)**2 for v in window)/20)/mean
    ma20 = sum(close[-20:])/20
    prev_ma20 = sum(close[-21:-1])/20
    # Signal is deliberately conservative: histogram crosses zero only on the latest bar.
    conditions = {
        "macd_negative_to_positive": hist[-2] <= 0 < hist[-1],
        "bollinger_width_expanding": bb_width(len(close)-1) > bb_width(len(close)-2),
        "close_above_rising_ma20": close[-1] > ma20 > prev_ma20,
    }
    r = rsi(close)
    # Divergence is a warning proxy: price makes a 20-day high, RSI does not
    # exceed the RSI peak of the preceding 20 days. This is NOT validated pivot divergence.
    divergence_warning = (
        close[-1] > max(close[-21:-1]) and
        r[-1] is not None and
        r[-1] < max(v for v in r[-21:-1] if v is not None)
    )
    return {"conditions": conditions, "candidate": all(conditions.values()),
            "rsi_divergence_proxy_warning": divergence_warning,
            "status": "RESEARCH_ONLY",
            "note": "No KD entry, stop-loss, position sizing, backtest, or live promotion implemented"}

