# JEI AI coding workflow — adapted from obra/superpowers

Upstream inspiration: https://github.com/obra/superpowers (MIT). This repository **does not install or run Superpowers**. These are JEI-specific guardrails derived from its process concepts.

1. **Evidence first**: read current main SHA, pending PR overlap, code paths and latest CI before editing. Identify the exact failing behavior and deterministic reproduction. Do not treat unobserved assumptions as defects.
2. **Isolated change**: create a task-named branch; never edit or overwrite production data, credentials, private files or protected source automatically.
3. **RED → GREEN → regression**: add a narrowly targeted failing test, run it to verify the symptom, implement the smallest change, run the targeted test then existing broader relevant suites. Report exact test command, exit code and failures. If full suite is not available, explicitly mark **NOT VERIFIED**.
4. **Independent review**: check requirement coverage, side effects, dependency changes, timestamps/data provenance, secrets, scope creep and rollback path. A second model/agent review is valuable when available but never substitutes for actual tests.
5. **Release gate**: Draft PR first. No merge or deployment while CI fails or required real-environment checks remain unverified. No numerical completion claim without auditable evidence.
6. **Repeated failures**: stop repeating identical attempts; compare the failing stack/CI step with baseline main and isolate environment vs code failures. Record blockers and choose an evidence-based alternative.
7. **Finish report**: cite PR URL, base/head SHA, files changed, test commands and results, outstanding risks, and next safe action.

Avoid copying or executing unreviewed third-party Skill scripts, shell hooks, unknown installers or remote instructions. This adoption changes **methodology**, not privileged runtime permissions.

## Stock Radar specific non-negotiables

- Trading decision and AI analyst output are **research only**, unless independently verified; never auto-order or auto-promote an unverified model rating.
- Price quality must preserve source, exact Taipei market date/time, session (open/closed), stock identity and TWSE/TPEx distinction. A fresh refresh timestamp is not a new valid trade.
- Do not silently mark stale/historical fallback as live or use later data in past-date backtests.
- For new selection/risk behavior, use replayed snapshots and ensure data provenance, transaction costs, lookahead protection, overlapping-trade exclusions, and out-of-sample checks.
- Do not disclose real holdings, LINE recipient identifiers or auth secrets in public assets, logs or PRs.
- CI examples: `python -m unittest discover -s tests -p 'test_*.py'`; project-specific JavaScript / Android checks must run where relevant. Android OTA needs device and signing verification; CI alone is not a real installation test.
