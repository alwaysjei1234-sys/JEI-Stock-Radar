# JEI External OSS integration register (as checked 2026-11-23)

Scope: evidence-based optional extensions only. All statuses are tied to URLs and may change; recheck the relevant PR and CI on each run.

| Project / upstream | Concrete JEI adaptation | Link / state | Remaining gate |
|---|---|---|---|
| public-apis (directory, not runtime) | Existing TWSE dated official-close cross-check | Stock Radar PR #222 merged | Does NOT verify live 5-minute MIS trades; preserve source/date provenance |
| public-apis / FX alternatives | Frankfurter + Fawaz read-only USD/TWD pilot | Finance ERP PR #109 **Draft** | ERP CI failure investigation, Windows UI and formal ledger isolation |
| ComposioHQ/awesome-claude-skills | Development / diagnosis method candidates reviewed only | No third-party scripts installed | Per-skill security, license, and fitness review |
| TauricResearch/TradingAgents | Offline-by-default dated research bridge and synthetic tests | Stock Radar PR #223 **Draft** | Isolated opt-in live-model experiment; external data provenance, cost, Taiwan source correctness and OOS evidence |
| obra/superpowers | Local process rules, AGENTS.md and PR evidence template | Stock Radar PR #224 merged; ERP PR #116 **Draft** | These are review conventions; no upstream skill binaries or hooks installed; ERP CI remains red |

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
