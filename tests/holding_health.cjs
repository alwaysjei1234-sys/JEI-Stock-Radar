const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('remote/holding-health.js', 'utf8');
const html = fs.readFileSync('remote/holding-health.html', 'utf8');
const root = {};
vm.runInNewContext(source, { window: root, Number, Math, JSON, Object, Array, Date });
const api = root.JEIHoldingHealth;
assert.ok(api, 'holding health module is exposed');
assert.equal(api.STORAGE_KEY, 'jei-holding-health-private-v1');

const holding = api.normalizeHolding({ code: '2330', name: '台積電', cost: '100', shares: '1000', price: '110' });
assert.deepEqual(JSON.parse(JSON.stringify(holding)), { code: '2330', name: '台積電', cost: 100, shares: 1000, price: 110 });
assert.throws(() => api.normalizeHolding({ code: '<img>', cost: 100, shares: 1000 }), /股票代號/);
assert.throws(() => api.normalizeHolding({ code: '2330', cost: 0, shares: 1000 }), /平均成本/);
assert.throws(() => api.normalizeHolding({ code: '2330', cost: 100, shares: 1.5 }), /整數/);
assert.equal(api.normalizeHolding({ code: '2330', cost: 100, shares: 1000, price: '' }).price, null);

const store = {
  value: null,
  getItem() { return this.value; },
  setItem(key, value) { this.key = key; this.value = value; },
  removeItem(key) { this.removed = key; this.value = null; }
};
const saved = api.save(store, [holding, { code: '0050', cost: 150, shares: 10, price: '' }]);
assert.equal(store.key, api.STORAGE_KEY);
assert.equal(api.load(store).length, 2);
const totals = api.summarize(saved);
assert.equal(totals.cost, 101500);
assert.equal(totals.marketValue, 110000);
assert.equal(totals.pnl, 10000);
assert.equal(totals.pricedCount, 1);
store.value = '{broken';
assert.deepEqual(JSON.parse(JSON.stringify(api.load(store))), []);

assert.match(html, /本機私人持股清單/);
assert.match(html, /不會傳送到 JEI 或 GitHub/);
assert.match(source, /textContent/);
assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|sendBeacon/);
console.log('PASS private holding ledger validation, local-only persistence, estimate math, and upload guard');
