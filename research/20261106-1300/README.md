# Health consistency replay

Run from repository root: `python research/20261106-1300/health_guard_replay.py --repo . --output /tmp/jei-health-replay.json`. Requires Python and git history containing 7475d41e4fea67beb9213e18251257197b49fbe0. No market access, personal holdings, credentials or orders. The pinned prior implementation is read from this trusted repository, compiled under an isolated module name, then compared with the current helper.

16 flag combinations and 8 universe/coverage cases; former false passes=13, current false passes=0. Normal inputs and input immutability retained. Synthetic diagnostics do not prove quote freshness or investment performance.

Design reference: https://github.com/pydantic/pydantic/blob/main/docs/concepts/validators.md and https://github.com/pydantic/pydantic/blob/main/LICENSE (MIT); no external implementation is copied or dependency added.
