"""Independent risk diagnostics for JEI's archived forward-only picks.

Uses only observed closes; does not claim executable intraday prices.
"""
from math import isfinite


def valid_close(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and value > 0)


def max_close_drawdown(entry_close, future_closes):
    """Peak-to-trough close drawdown, including the original signal close."""
    if not valid_close(entry_close):
        raise ValueError("Invalid signal close")
    peak = float(entry_close)
    worst = 0.0
    for close in future_closes:
        if not valid_close(close):
            raise ValueError("Missing or invalid close")
        peak = max(peak, float(close))
        worst = min(worst, (float(close) / peak - 1) * 100)
    return round(worst, 3)


def duplicate_signal_summary(picks):
    """Count category duplicates without erasing each original recommendation."""
    unique = {(p["day"], p["code"]) for p in picks}
    return {
        "category_recommendations": len(picks),
        "unique_day_symbol_signals": len(unique),
        "cross_category_duplicates": len(picks) - len(unique),
    }
