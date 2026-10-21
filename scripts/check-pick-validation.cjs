#!/usr/bin/env node
// JEI performance feed integrity check. Run: node scripts/check-pick-validation.cjs
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const feed = JSON.parse(fs.readFileSync(path.join(__dirname, '../remote/pick_validation.json'), 'utf8'));
assert.equal(feed.mode, 'forward_official_close_pick_validation');
assert.ok(Array.isArray(feed.picks), 'picks must be an array');
assert.equal(feed.total_frozen_picks, feed.picks.length, 'frozen pick count mismatch');
assert.ok(Array.isArray(feed.horizons_trading_days));
const ids = new Set();
for (const p of feed.picks) {
  assert.ok(p && p.id && p.day && p.code && Array.isArray(p.outcomes), 'invalid pick');
  assert.ok(!ids.has(p.id), 'duplicate pick ID: ' + p.id);
  ids.add(p.id);
  for (const o of p.outcomes) {
    assert.ok(Number.isInteger(o.trading_days) && feed.horizons_trading_days.includes(o.trading_days), 'invalid horizon');
    assert.ok(['complete', 'pending', 'missing_price'].includes(o.status), 'invalid outcome status');
    if (o.status === 'complete') {
      assert.ok(Number.isFinite(o.estimated_net_return_pct) && o.end_day, 'complete outcome missing return or end date');
      assert.ok(o.end_day >= p.day, 'outcome predates recommendation');
    }
  }
}
const official = Date.parse(String(feed.latest_official_day || '') + 'T00:00:00+08:00');
assert.ok(Number.isFinite(official), 'invalid official close date');
assert.ok(official <= Date.now(), 'future official close date');
for (const [strategy, horizons] of Object.entries(feed.groups || {})) {
  for (const [days, group] of Object.entries(horizons)) {
    assert.ok(feed.horizons_trading_days.includes(Number(days)), 'unexpected horizon');
    for (const k of ['completed', 'pending', 'missing_price']) {
      assert.ok(Number.isInteger(group[k]) && group[k] >= 0, strategy + '/' + days + ': invalid ' + k);
    }
    if (group.completed === 0) assert.equal(group.win_rate_pct, null, 'zero completed must not claim win rate');
    const observations = feed.picks.filter(p => p.group === strategy).map(p => p.outcomes.find(o => o.trading_days === Number(days)));
    assert.ok(observations.every(Boolean), strategy + '/' + days + ': missing outcome');
    for (const [status, key] of [['complete', 'completed'], ['pending', 'pending'], ['missing_price', 'missing_price']]) {
      assert.equal(observations.filter(o => o.status === status).length, group[key], strategy + '/' + days + ': ' + key + ' mismatch');
    }
    const completed = observations.filter(o => o.status === 'complete');
    if (completed.length) {
      const winRate = Math.round(completed.filter(o => o.estimated_net_return_pct > 0).length / completed.length * 10000) / 100;
      assert.ok(Math.abs(winRate - group.win_rate_pct) < 0.011, strategy + '/' + days + ': win rate mismatch');
      const avg = completed.reduce((sum, o) => sum + o.estimated_net_return_pct, 0) / completed.length;
      assert.ok(Math.abs(avg - group.avg_estimated_net_pct) < 0.011, strategy + '/' + days + ': average net return mismatch');
    }

  }
}
console.log('PASS: JEI pick validation integrity (' + feed.picks.length + ' picks)');
