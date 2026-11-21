"""Deterministic, no-lookahead paper-trading baseline for JEI DQN comparisons."""
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    close: float

@dataclass(frozen=True)
class Signal:
    date: str
    action: str  # BUY, SELL, HOLD; generated AFTER that day's close


def simulate(bars: Iterable[Bar], signals: Iterable[Signal], cash=1_000_000., fee_rate=0.001425, tax_rate=0.003, slippage=0.001):
    """Execute prior-day close signals at next available session open; long-only, 1000-share lots."""
    bars = list(bars)
    signals = list(signals)
    if any(b.open <= 0 or b.close <= 0 for b in bars):
        raise ValueError('Invalid price')
    if any(bars[i].date >= bars[i+1].date for i in range(len(bars)-1)):
        raise ValueError('Bars must have unique ascending dates')
    if len({s.date for s in signals}) != len(signals):
        raise ValueError('Duplicate signal date')
    if any(s.action not in ('BUY','SELL','HOLD') for s in signals):
        raise ValueError('Unknown action')
    by_date = {s.date:s.action for s in signals}
    shares = 0
    trades = []
    equity = []
    pending = None
    for bar in bars:
        if pending == 'BUY':
            price = bar.open * (1+slippage)
            lots = int(cash // (1000*price*(1+fee_rate)))
            qty = lots*1000
            if qty:
                cost = qty*price*(1+fee_rate)
                cash -= cost
                shares += qty
                trades.append({'date':bar.date,'side':'BUY','qty':qty,'price':price,'cash':cash})
        elif pending == 'SELL' and shares:
            price = bar.open*(1-slippage)
            qty = shares
            cash += qty*price*(1-fee_rate-tax_rate)
            shares = 0
            trades.append({'date':bar.date,'side':'SELL','qty':qty,'price':price,'cash':cash})
        pending = by_date.get(bar.date)
        equity.append({'date':bar.date,'equity':round(cash+shares*bar.close,2)})
    return {'trades':trades,'equity':equity,'ending_cash':round(cash,2),'ending_shares':shares}
