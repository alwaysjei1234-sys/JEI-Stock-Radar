# JEI compute continuity and Colab monitoring

## Verified architecture

- GitHub Actions runs the portable observed-performance computation hourly and uploads an artifact even when Colab is offline.
- A live Colab notebook can start a 5-minute Drive heartbeat; the kernel must be running.
- The hourly audit reads the heartbeat **only if** a read-only Google service account and heartbeat file ID have been configured. Missing credentials or an inaccessible file result in UNKNOWN, not STALE.
- The watchdog never remotely restarts Colab. Free Colab runtime availability and reconnection cannot be guaranteed.
- `tools/jei_batch_checkpoint.py` provides atomic, source-hash-and-parameters-bound checkpoints for future batch workers. It does not yet implement historical trade simulation.

## One-time credential setup required

1. Create a dedicated Google Cloud service account with Drive read-only scope. Keep its JSON private; never put it in GitHub files or chats.
2. In Colab, mount Drive and run the heartbeat notebook cell once. Share only the generated `JEI-Stock-Radar/diagnostics/colab_heartbeat.json` with the service account email as Viewer.
3. Add the service account JSON to GitHub Actions repository secret `JEI_DRIVE_SERVICE_ACCOUNT_JSON`.
4. Add the heartbeat file's Drive ID to GitHub Actions repository variable `JEI_COLAB_HEARTBEAT_FILE_ID`.
5. Run the `JEI Compute Provenance Audit (GitHub Actions)` workflow and inspect `colab_watchdog.json` in its artifact. Check that `drive_access=authenticated`, then verify fresh and stale transitions using an actual Colab session.

## Cross-chat usage

The source of truth is `alwaysjei1234-sys/JEI-Stock-Radar` main and GitHub Actions artifacts. Other chats should check main SHA, latest audit artifact, watchdog status and data hash rather than trusting earlier chat claims.

## Outstanding work

- Live Colab start and Drive authorization (requires an actual authenticated session).
- True Colab interruption and resume test, with checkpoint integration into a historical per-trade backtester.
- Independent OOS trades, realistic fees, slippage and strategy performance verification.
