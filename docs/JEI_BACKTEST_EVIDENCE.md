# JEI independent OOS trade evidence

Run `python -m tools.jei_trade_backtest --trades path/to/trades.csv --cost 0.005`.

Required CSV headers: `strategy_id,ticker,entry_date,exit_date,gross_return,regime,split`.
Dates are ISO YYYY-MM-DD; gross_return is a decimal fraction, not percent; split is train or oos. Cost is a *round-trip fraction* and must be supplied from a defensible fee/tax/slippage assumption. The evaluator refuses overlapping trades on the same strategy and ticker, computes cost-adjusted win rate, expectancy, max drawdown and number of distinct market regimes.

**Limitations:** This evaluator uses supplied closed trades, not price histories. It cannot independently prove prices, prevent fabricated trade records, rule out lookahead, establish walk-forward split integrity or model independence. Its outputs MUST NOT be treated as sufficient for live promotion. The evolution gate requires separate verified provenance and no-lookahead evidence. Never put private holdings or API credentials in the public repository.
