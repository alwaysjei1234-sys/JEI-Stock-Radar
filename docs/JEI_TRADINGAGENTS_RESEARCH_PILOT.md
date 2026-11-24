# JEI Stock Radar × TradingAgents — isolated research pilot

Upstream: https://github.com/TauricResearch/TradingAgents (pin and review upstream release before actual installation).

## Actual scope

- `tools/jei_tradingagents_bridge.py` takes one code, market and historical date, validates existing JEI `remote/daily_prices.json`, and emits **dry-run research metadata** by default.
- For Taiwan, `TWSE` maps to `.TW` and `TPEx` maps to `.TWO`. This is an identity mapping, not a vendor quote check.
- The date-labelled archive is **only a JEI-side provenance gate**. Upstream TradingAgents fetches **its own Yahoo/SEC/etc feeds** when invoked; no JEI prices, verified institutional holdings, five-minute quotes or private holdings are injected.
- Model analysis and BUY/SELL ratings are **never actionable** in this pilot; no change to JEI selection ranks, signals, LINE, Android, backtests, paper trades, private holdings, financial ERP or orders.
- No upstream package is added to requirements or runtime. CI executes only deterministic offline mocks.
- Upstream HTML reports, artifacts, external data transfers, API use, and actual model performance remain **unverified**. SEC filings are not proof that all non-US company data is point-in-time sound.

## Offline verification

```sh
python -m unittest discover -s tests -p 'test_jei_tradingagents_bridge.py' -v
python -m tools.jei_tradingagents_bridge --market TWSE --code 1101 --date 2026-11-03
```

The default command never calls models or makes network requests. Dates must be present in the archive.

## Explicit experimental run (not automatic CI, requires local setup)

Install and review the upstream project in a dedicated Python 3.11+ environment, pinning a tested release. Log in explicitly if using the ChatGPT subscription provider; the upstream sign-in is **not** the OpenAI API and usage follows account access and plan limits. For local Ollama, independently install and configure Ollama.

```sh
JEI_ENABLE_EXTERNAL_AI_RESEARCH=1 TRADINGAGENTS_LLM_PROVIDER=ollama \
python -m tools.jei_tradingagents_bridge --market TWSE --code 1101 --date 2026-11-03 --execute
```

A live experiment may contact upstream news/quote vendors, use tokens, create model caches and save external logs. Do not pass private portfolio, credentials or brokerage access. Authenticate locally only; never put tokens in GitHub. No guarantee of free inference or correct Taiwan fundamentals.

## Acceptance checklist

1. Run offline tests; verify input failures and unchanged archived prices.
2. Manually verify TradingAgents release, dependencies, terms and external model settings.
3. Check market suffix and source-date alignment with Taiwan exchange data.
4. Compare AI report with verified JEI evidence; reject undated or future-dated factual claims.
5. Require out-of-sample comparison including trading costs before any production consideration.
6. Human review before release. Reject promotion to orders or real-time signals.
