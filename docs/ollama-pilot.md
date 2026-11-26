# JEI optional Ollama pilot

This is a disabled-by-default experiment. Existing stock feeds, indicators, alerts and schedules do not change.

1. On a supported Windows PC, install Ollama from https://ollama.com/download/windows.
2. Install the local model with `ollama pull qwen3:4b`. Do not expose port 11434 externally. Disable Ollama cloud features and verify offline inference before permitting any restricted content.
3. Run `python jei_local_ai_router.py --probe` on that PC. A remote runner's loopback is not the user's PC.
4. Run `python jei_local_ai_router.py --self-test` to verify the routing policy.

Public research can be considered for local inference only when explicitly enabled and the model is present. Otherwise the decision points to the existing cloud pipeline; it does not launch that pipeline. Restricted or unclassified jobs are held, even if the health check succeeds. No holdings, bank records, credentials or prompts are transmitted by this pilot.

Next acceptance gates: separate local inference worker, strict request/response validation, opt-in public task queue, idempotent job IDs and leases, simulated disconnect/reconnect, retry limits, measured latency and model quality. Public cloud fallback must reuse existing schedules and must not double-send alerts. Finance ERP integration is a separate task; no accounting ledger writes or cloud fallback for private data. No paid services required by this pilot; usage limits on existing cloud services remain.

## Colab coordination
The pilot now accepts the existing coordination JSON as an advisory input. It selects a Colab candidate only for explicitly public, opt-in tasks when local is unavailable, the status is ACTIVE with authenticated Drive heartbeat evidence, and the caller independently verifies freshness and task capability. ACTIVE is a provisional positive status contract; confirm the producer's actual enumeration before connecting the dispatcher. STALE, unknown or unsupported tasks preserve the existing cloud pipeline (which owns Actions fallback). No job is dispatched by the router. Next: wire the actual heartbeat verifier and worker capability registry; exercise handoff with unique job IDs and acknowledgements. Never keep free Colab sessions alive through artificial activity or bypass usage limits.
