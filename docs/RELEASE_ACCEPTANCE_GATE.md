# JEI Stock Radar — release acceptance gate

This checklist is a **manual verification protocol**, not a claim that tests passed. Record evidence before advertising a release as verified.

## 1. Data freshness and safety
- [ ] Verify the Taiwan-local trading calendar, weekend/holiday handling and 13:30 official close. Never label pre-close data as final close.
- [ ] Compare displayed price, quote timestamp and ticker against the upstream exchange response for a holding, a top pick and an alphanumeric ETF.
- [ ] Force network failure, timeout, malformed JSON and stale timestamps; confirm clear stale/unavailable labels and no fabricated prices.
- [ ] Ensure public remote feeds, logs and screenshots contain no private positions, cost basis, API keys or LINE credentials.

## 2. Android end-to-end
- [ ] Install the published APK on a physical Android device; cold-start online and offline.
- [ ] Confirm remote UI updates when valid, and bundled UI fallback when remote download fails.
- [ ] Enter/edit a holding; force-stop and relaunch; confirm quantity and cost persist locally.
- [ ] Verify holding quotes refresh after resume and do not get starved by full-market scanning.
- [ ] Verify remote update metadata, version comparison and safe handling of broken URLs.
- [ ] Test an ETF code containing letters and a delisted/unknown symbol.

## 3. Forward-only paper trading
- [ ] Freeze each daily pick with an immutable as-of timestamp, code, signal, ranking, entry rule and source snapshot.
- [ ] Confirm no future price or report can change the historical candidate list or entry price.
- [ ] Report 3/7/15/30/60 **trading-session** outcomes only after the corresponding sessions mature.
- [ ] Mark insufficient/missing prices as pending or unavailable; never score them as wins or drop losing picks silently.
- [ ] Separate momentum, monster-stock and pre-breakout cohorts; compare against a dated benchmark.
- [ ] Include fees, tax and slippage assumptions, drawdown, win rate, sample count and survivorship-bias cautions.
- [ ] Keep cash-equity paper trading independent from intraday simulation and live brokerage execution.

## 4. Research evidence
- [ ] Show original institutional source, publication date, link and independent organization count.
- [ ] Deduplicate same-organization reports and flag stale evidence or contrary findings.
- [ ] Never upgrade an individual stock merely because its sector outlook is favorable.

## 5. Notifications and release decision
- [ ] Test LINE delivery with a harmless test message, a simulated risk event and a duplicate event.
- [ ] Verify alert deduplication, quiet-hours policy and recovery from rate limits/network errors.
- [ ] Archive test run ID, commit SHA, APK version, device/Android version and screenshots.
- [ ] Mark each gate PASS / FAIL / NOT RUN. Release is not "90% verified" while critical gates remain NOT RUN.

## Suggested minimum acceptance order
1. Static tests and CI checks.
2. Market feed freshness and invalid-data cases.
3. Paper-trading historical immutability and forward scorecard.
4. Android online/offline cold-start and holdings persistence.
5. LINE end-to-end delivery.
6. Publish release evidence and only then update completion claims.
