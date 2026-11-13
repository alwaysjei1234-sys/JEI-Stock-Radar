# Blave Agent × JEI — isolated validation pilot

Status: experimental; **not deployed**, not connected to live brokerage accounts.

Upstream: https://github.com/Blave-TW/blave-agent (Apache-2.0; verify notices and attribution before copying code).

## Current JEI boundaries
- Keep Android WebView, `remote/index.html`, `remote/system.json`, and existing LINE pipelines unchanged.
- No trading keys, personal holdings, or private access codes in public repository or feeds.
- No order execution. Paper trading only, using timestamped signals and immutable historical snapshots.
- Do not infer a measured improvement to JEI completion percentage from this document.

## Proposed adapter contract (future implementation)
Input: UTF-8 JSONL records with:
`signal_id`, `generated_at` (ISO-8601 with timezone), `ticker`, `market` ("TW"), `strategy_id`, `signal` ("BUY"/"SELL"/"HOLD"), `reference_price`, `data_asof`, `source`.
Reject duplicates, missing prices, future-dated source data, and non-trading-day execution assumptions.

Output: separate JSON report with per-signal entry/exit timestamps, simulated fees, slippage, realized/unrealized P&L, and 3/7/15/30-trading-day horizon statistics. Clearly distinguish observed results from incomplete/open positions.

## Validation gates
1. Audit Blave Taiwan-stock data source, license, dependency versions and API compatibility.
2. Create reproducible fixtures and test signal parsing, look-ahead leakage, timezone and TW market calendar.
3. Compare JEI backtest with Blave on the **same** price series, costs, and fill rules.
4. Walk-forward out-of-sample validation; report sample size, confidence intervals, drawdown, and fee-adjusted win rate. **80% is a target, not a claim**.
5. CI passes and human review before merging; retain rollback path.
6. Only after paper results are verified, evaluate a read-only summary feed for the mobile app.

## Immediate blockers
- Blave desktop and JEI Android/Vercel do not share a drop-in runtime.
- Upstream paper trading support does not establish Taiwan-stock paper execution compatibility.
- Live LINE delivery must be independently diagnosed; Blave alone will not fix it.
