# JEI Multi-AI evolution: staged integration

This is a safety gate, **not** an autonomous model runner or proof of improved returns.

1. Independent researcher and critic must come from distinct model IDs/providers, with explicit provenance. Never put API keys or holdings in public repo.
2. Save each candidate strategy with commit SHA, immutable market snapshot and backtest version. Require transaction fees, taxes, slippage, overlapping-trade removal and lookahead checks.
3. Run out-of-sample, walk-forward evaluations across at least three market regimes, with at least 100 non-overlapping closed trades.
4. Execute `python -m tools.jei_evolution_gate --input proposals/private-evaluation.json` in a secure environment. Candidate must beat baseline on net expectancy, not worsen drawdown, and reach 80% win rate to receive **REVIEW**, not deploy.
5. REVIEW creates an auditable human-reviewed pull request. REJECT keeps the existing production strategy unchanged.
6. Model connectors, live historical dataset, reliable backtest runner, and promotion pipeline are NOT YET connected. Do not claim self-evolution is live or 60% complete.
