# TWSE STOCK_DAY × daily_prices consistency guard

This optional **read-only** check compares already stored date-labelled TWSE
`STOCK_DAY` observations with `remote/daily_prices.json` for the **same day
and stock code**. It adds no separate exchange and **must never** be treated
as independent market verification or a new 5-minute live quote source.

Example after existing archive collection:

```bash
python scripts/crosscheck_official_closes.py \
  --daily remote/daily_prices.json \
  --snapshots data/twse_ohlcv/1101-202611.json
```

Exit codes: `0` = consistent with overlap; `1` = discrepancy/no overlapping
sessions; `2` = invalid input. Results have source/date and mismatch details,
are printed only, and never modify the official archives, live feed, trade
signals, scoring or simulation results.

`STOCK_DAY` historical pulls can lag the latest day. Run on dated sessions only
and never infer the data date from request time.
