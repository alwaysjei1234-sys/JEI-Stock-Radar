"""Descriptive diagnostics for frozen paper trades; never changes fills or rules."""
import math


def wilson_interval(wins, count):
    if count == 0:
        return None
    z = 1.959963984540054
    p = wins / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count)) / denominator
    radius = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count)) / denominator
    return [round(100*max(0, center-radius), 2), round(100*min(1, center+radius), 2)]


def trade_metrics(trades, fee, sell_tax):
    """Same quantities and exit dates; stress is not a portfolio replay."""
    values = []
    for trade in trades:
        try:
            if any(isinstance(trade.get(key), bool) for key in ('entry_price', 'exit_price', 'qty', 'net')):
                raise ValueError('Boolean paper trade value')
            entry, exit_price, qty, net = (float(trade[key]) for key in ('entry_price', 'exit_price', 'qty', 'net'))
            if not all(math.isfinite(x) for x in (entry, exit_price, qty, net)) or min(entry, exit_price, qty) <= 0:
                raise ValueError('Invalid paper trade')
            cost = entry * qty * (1 + fee)
            proceeds = exit_price * qty * (1 - fee - sell_tax)
            # Refuse stress/interval statistics from an inconsistent legacy ledger.
            if abs((proceeds-cost) - net) > 0.011:
                raise ValueError('Paper trade cost mismatch')
            values.append((entry, exit_price, qty, net, cost))
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError('Invalid paper trade') from exc
    count = len(values)
    wins = sum(row[3] > 0 for row in values)
    profit = sum(max(0, row[3]) for row in values)
    loss = -sum(min(0, row[3]) for row in values)
    scenarios = []
    for rate in (0.001, 0.002):
        returns = []
        for entry, exit_price, qty, net, cost in values:
            stressed_cost = cost*(1+rate)
            stressed_proceeds = exit_price*qty*(1-rate)*(1-fee-sell_tax)
            returns.append(100*(stressed_proceeds/stressed_cost-1))
        scenarios.append({'slippage_per_side_pct': rate*100, 'closed': count,
                          'win_rate_pct': round(100*sum(x>0 for x in returns)/count, 2) if count else None,
                          'mean_net_return_pct': round(sum(returns)/count, 3) if count else None})
    minimum_fee_scenarios = []
    # Hypothetical fee floors, not the user's broker tariff. Apply each floor
    # to brokerage alone; the sell-side transaction tax remains separate.
    for minimum in (1.0, 20.0):
        for rate in (0.0, 0.001):
            returns, pnls, affected, extra_fees = [], [], 0, 0.0
            for entry, exit_price, qty, net, cost in values:
                bought = entry*qty*(1+rate)
                sold = exit_price*qty*(1-rate)
                buy_fee, sell_fee = max(minimum, bought*fee), max(minimum, sold*fee)
                extra = buy_fee-bought*fee + sell_fee-sold*fee
                affected += extra > 1e-9
                extra_fees += extra
                entry_cost = bought+buy_fee
                pnl = sold-sell_fee-sold*sell_tax-entry_cost
                pnls.append(pnl)
                returns.append(100*pnl/entry_cost)
            minimum_fee_scenarios.append({
                'minimum_fee_per_side_ntd': minimum,
                'slippage_per_side_pct': rate*100, 'closed': count,
                'affected_trades': affected,
                'additional_commission_ntd': round(extra_fees, 2),
                'win_rate_pct': round(100*sum(x>0 for x in pnls)/count, 2) if count else None,
                'mean_net_return_pct': round(sum(returns)/count, 3) if count else None,
                'mean_net_pnl_ntd': round(sum(pnls)/count, 2) if count else None,
                'scope': 'fixed_closed_trades_only',
            })
    return {'closed': count, 'win_rate_ci95_pct': wilson_interval(wins, count),
            'mean_net_return_pct': round(sum(100*r[3]/r[4] for r in values)/count, 3) if count else None,
            'profit_factor': round(profit/loss, 3) if loss else None,
            'profit_factor_note': 'measured' if loss else 'no_realized_losses' if count else 'no_closed_samples',
            'slippage_scenarios': scenarios,
            'minimum_fee_scenarios': minimum_fee_scenarios,
            'qualification': 'research_only',
            'notes': '勝率區間是描述性估計；同日、同股與重疊交易相關，不能當獨立樣本或樣本外驗證。滑價及最低手續費僅重估原平倉、股數與日期，不重跑資金配置、出場或未平倉部位；不代表可成交。最低費1／20元僅為每邊手續費假設，非使用者實際費率，賣出稅另計；不修改原帳本，未重算情境投組回撤。'}


def full_drawdown(history, capital):
    # Missing marked-to-market equity can conceal a deeper trough. Do not
    # silently certify the surviving subsequence as the full-path drawdown.
    peak, worst, available, missing = capital, 0.0, False, False
    for row in history:
        value = row.get('equity')
        if value is None:
            missing = True
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid paper equity')
        available = True
        peak = max(peak, value)
        worst = max(worst, 100*(peak-value)/peak)
    return round(worst, 3) if available and not missing else None
