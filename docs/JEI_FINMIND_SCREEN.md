# JEI financial-stock flow / revenue / MA screen

This is a deterministic screen for validated exported CSV data, **not** a live FinMind API connector. It implements the requested financial-stock conditions with a precise definition: rolling 20 trading sessions trust net buy **greater than 5,000 lots** (5,000,000 shares), last disclosed monthly revenue YoY **greater than 20 percent**, and closing price **below a 60-session moving average**. No historical lookahead: revenue_publish_date must be on or before trade_date.

Usage: `python -m tools.jei_finmind_screen --csv path/to/verified.csv --as-of 2026-11-06`.

Required headers: `ticker,sector,trade_date,close,ma60,trust_buy_shares_20d,revenue_yoy_pct,revenue_publish_date`. Input trade date is ISO, revenue YoY in percent (25 means 25%). No trades, rankings, real market quotes or performance are invented. Source extraction, Taiwan financial-sector classification, FinMind rate limits and raw API-to-CSV adapters still require implementation and verification.
