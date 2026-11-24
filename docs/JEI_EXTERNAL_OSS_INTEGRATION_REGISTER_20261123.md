# JEI External OSS integration register (as checked 2026-11-23)

Scope: evidence-based optional extensions only. All statuses are tied to URLs and may change; recheck the relevant PR and CI on each run.

| Project / upstream | Concrete JEI adaptation | Link / state | Remaining gate |
|---|---|---|---|
| public-apis (directory, not runtime) | Existing TWSE dated official-close cross-check | Stock Radar PR #222 merged | Does NOT verify live 5-minute MIS trades; preserve source/date provenance |
| public-apis / FX alternatives | Frankfurter + Fawaz read-only USD/TWD pilot | Finance ERP PR #109 **Draft** | ERP CI failure investigation, Windows UI and formal ledger isolation |
| ComposioHQ/awesome-claude-skills | Development / diagnosis method candidates reviewed only | No third-party scripts installed | Per-skill security, license, and fitness review |
| TauricResearch/TradingAgents | Offline-by-default dated research bridge and synthetic tests | Stock Radar PR #223 **Draft** | Isolated opt-in live-model experiment; external data provenance, cost, Taiwan source correctness and OOS evidence |
| obra/superpowers | Local process rules, AGENTS.md and PR evidence template | Stock Radar PR #224 merged; ERP PR #116 **Draft** | These are review conventions; no upstream skill binaries or hooks installed; ERP CI remains red |

## Additional user-supplied references — reviewed 2026-11-24

These are **capability references**, not authenticated data sources or evidence of
working external integrations. Never copy scripts or executable hooks by default.

| Reference | Use within JEI | Verified code state | Next safe gate |
|---|---|---|---|
| [Blave Agent](https://github.com/Blave-TW/blave-agent) | Strategy export / paper-performance comparison | `tools/jei_blave_bridge.py` offline JSONL adapter and regressions exist | Real export, source-time checks, no order API; independent OOS still unverified |
| [Deep Q-learning example](https://github.com/sachink2010/AutomatedStockTrading-DeepQ-Learning) | Experiment with reinforcement-learning actions under honest train/OOS split | `tools/jei_dqn_oos_bridge.py` read-only adapter with synthetic tests | Authenticated model training artifacts and walk-forward holdout; never silently claim 80% wins |
| [E2B](https://github.com/e2b-dev/E2B) | Optional isolated code execution / agent experiments | **Not connected to JEI** | Free-tier/cost, secret scope, isolated workspace and outbound-network review before adding dependency |
| [HeyChengC wallstreet-explainer](https://github.com/HeyChengC/wallstreet-explainer) | Finance/tech educational explainer and video layout ideas | **Not integrated into selection or models** | Review video asset licensing and generation costs; keep outside trading decision path |
| [Teamily AI](https://teamily.ai/) | Optional public-news/market multi-agent research comparison | Documentation only in `docs/RESEARCH_SOURCES_FOREXFACTORY_TEAMILY.md` | Confirm usable endpoint, authentication, pricing and citation provenance; no private holdings |
| [Forex Factory](https://www.forexfactory.com/) | Macro event discovery for risk calendar | Documentation only; not official Taiwan prices | Cross-verify CPI/FOMC/NFP from primary publisher before publishing |
| [Public APIs](https://github.com/public-apis/public-apis) | Directory of potentially free feeds, not a market data provider itself | Official Taiwan source cross-check in existing PR #222 | Independently review provider licenses, availability and timestamp; never treat a directory as data |
| [Composio Skills](https://github.com/ComposioHQ/awesome-claude-skills) | Candidate connector workflow ideas | **No third-party skills installed** | Human review of specific skill, OAuth scope and commands before any write-capable integration |

**Priorities for Stock Radar:** (1) TWSE/TPEx price provenance and true live freshness,
(2) real research-only multi-agent bridge / conflict check, (3) costly/noisy external
feed minimization, (4) forward-frozen 3/7/15/30-day performance with cost and
no lookahead, (5) UI explainability and optional content tooling.

The TradingAgents pilot in this PR now includes an actual checked-in JEI
`remote/daily_prices.json` replay test in addition to mocked source tests.
This is **not a real model call**, **not independent OOS** and **not a deployed trading agent**.

## Ownership and boundaries
- **Stock Radar owns** trade-date provenance, TWSE/TPEx/MIS verification, stock candidates, scenarios, market risk, simulated performance, Android and LINE.
- **TradingAgents is** an optional external *research-only* evaluator after a JEI-side dated archive check. It is not a verified primary market feed or autonomous trading executor.
- **ERP owns** accounting FX, audited bank ledger, company and investment attribution, Windows installer, backups and official owner reports. Public FX must never post into finance records.
- **Superpowers / Skills** are process instructions, not new compute, inference credits or a guarantee of CI success. Never run a downloaded third-party skill with repo write or credential access without code review.

## Next safe evidence checkpoints
1. PR #223 CI, then optional isolated model call when an environment is explicitly configured and the model provider is authorized by its owner.
2. Compare upstream answer with exact TWSE/TPEx or SEC published date and source; reject unverifiable claims.
3. Keep AI review informational until verified independent walk-forward OOS results and transaction cost accounting exist.
4. Finance ERP PR #109 and #116 remain isolated until CI blockers and Windows tests are resolved.
