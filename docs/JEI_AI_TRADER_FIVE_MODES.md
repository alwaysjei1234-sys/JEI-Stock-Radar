# JEI AI trader: five analysis modes

## User-confirmed preference
- Primary market: Taiwan equities; secondary: US equities
- Style: swing trading and strong-stock momentum trends
- Risk appetite: aggressive **with explicit risk controls**
- Analysis priorities: dominant capital flow, technical, institutional flows, fundamentals, news
- Never claim actual 30 years of human trading experience. Use historical comparisons and evidence-based professional frameworks.

## Mode contracts
1. **Market news**: true mechanism, affected markets (stocks, bonds, USD, gold, crypto where relevant), short/long horizon, market narrative, historical analogues; conclude bullish/bearish/next step.
2. **Technical**: trend, support/resistance, volume, RSI/MACD/MAs, price structure, institutional accumulation/distribution hypotheses with uncertainty, breakout vs fakeout vs reversal vs range; conclude strength, key levels, scenarios.
3. **Fundamental**: sales/EPS, margins, cash flow, moat, valuation, growth, key filings; conclude actual strengths and market concerns.
4. **AI decision**: cross-check news/technical/fundamental/sentiment/capital flow; identify contradictory signals and main risk; output bullish/bearish/neutral and attack/wait/defend with scenario invalidation.
5. **Personalized trader**: apply profile weighting and risk controls; never turn a qualitative AI report into an order.

## Implementation boundary
The current module defines report contracts and user preferences, **not** actual LLM calls, source fetching, backtesting, or production trading. A report is incomplete unless data timestamp, cited sources, facts versus hypotheses, and invalidation conditions are supplied. Real signals require independently verified quotes and historical out-of-sample tests; no auto trade or auto promote.
