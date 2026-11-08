# JEI 3-stage AI prompt optimization

User-approved flow:
1. Initial analysis and answer, only from verified market/fundamental/technical data, otherwise explicitly mark pending.
2. Diagnose prompt blind spots: symbol, market, as-of, horizon, strategy, risk limits, benchmark, data provenance, OOS backtest period.
3. Produce a reusable upgraded prompt, emphasizing evidence, contradictions, invalidation, and no fabricated performance.

`tools/jei_prompt_optimizer.py` implements a **deterministic three-stage report skeleton and prompt generator** using the user-confirmed AI trader profile. It does **not** call an LLM, fetch market data, prove 30 years of experience, or execute trades. Actual analysis generation requires source adapters and a model provider; future implementations must preserve missing-data states and prevent automated promotion without independent backtest evidence.
