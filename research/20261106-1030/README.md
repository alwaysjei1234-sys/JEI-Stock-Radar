# Quote-date versus freshness experiment

Research only. No external source is copied into the JEI product. Original project MIT, last push 2026-09-17T14:22:16Z.

Read source: https://raw.githubusercontent.com/jiawei-hong/tw-stock-cli/93d3627e377b2f2ab0f274d194e5a07bcdd5874a/src/commands/stock/quote-status.ts
Expected SHA256: ff62d6a057fe9bfa38c5c55f42718347e210b7e444449f16969528f176d7479e

To reproduce from the repository root with Node 24 and Python 3.12:

1. Download that exact source to research/20261106-1030/cli_src_commands_stock_quote-status.ts (not tracked).
2. Run `node research/20261106-1030/compare_freshness.mjs`. The harness checks SHA256, removes only the type-only TStock import and uses Node's experimental stripTypeScriptTypes; no third-party dependencies or network calls during execution.
3. Run `python research/20261106-1030/compare_jei.py --repo .`. MIS is mocked; no real orders, user credentials or personal holdings.

8 original pure-function cases and 8 JEI quote replays. At fixed 2026-11-06 10:30 Taipei, CLI labels a same-date quote 今日成交 even if its time is old, future, missing or its price is zero. That label is date classification, not an age guarantee; the project's README warns timestamps still need checking. JEI accepts only the single fresh valid execution. This is not a whole-project comparison or evidence of investment returns.

Static review also covered original stock/api.ts, utils/http.ts and quote-status tests; HTTP wrapper bounds retries and normalizes timeout/delay, checks MIS rtcode. JEI already has bounded probes, application-status and identity gates. No SDK or batch-size changes adopted without live reliability comparison.
