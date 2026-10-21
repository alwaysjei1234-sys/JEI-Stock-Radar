#!/usr/bin/env node
// Regression checks: corrupted performance data must fail closed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const source = JSON.parse(fs.readFileSync(path.join(__dirname, '../remote/pick_validation.json'), 'utf8'));
const checker = path.join(__dirname, 'check-pick-validation.cjs');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jei-picks-'));
function check(data, expectedSuccess, label) {
  const file = path.join(dir, 'fixture.json');
  fs.writeFileSync(file, JSON.stringify(data));
  const result = spawnSync(process.execPath, [checker, file], { encoding: 'utf8' });
  assert.equal(result.status === 0, expectedSuccess, label + ': ' + result.stderr);
}
function mutated(fn) { const data = structuredClone(source); fn(data); return data; }
try {
  check(source, true, 'official feed');
  check(mutated(d => { d.total_frozen_picks++; }), false, 'incorrect pick count');
  check(mutated(d => { d.picks[1].id = d.picks[0].id; }), false, 'duplicate ID');
  check(mutated(d => { d.groups.attack['3'].completed++; }), false, 'incorrect completed count');
  check(mutated(d => { d.groups.attack['3'].win_rate_pct = 99; }), false, 'fabricated win rate');
  check(mutated(d => { d.groups.attack['3'].avg_estimated_net_pct = 99; }), false, 'fabricated return');
  check(mutated(d => { d.latest_official_day = '2999-01-01'; }), false, 'future date');
  console.log('PASS: seven JEI feed integrity regression cases');
} finally {
  fs.rmSync(dir, { recursive: true, force: true });
}
