const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync('remote/holding-health.js', 'utf8');
const html = fs.readFileSync('remote/holding-health.html', 'utf8');
const root = {};
vm.runInNewContext(source, { window: root, Number, Math, JSON, Object, Array, Date, TextEncoder, TextDecoder, btoa, atob, Uint8Array, Map, Set });
const api = root.JEIHoldingHealth;
assert.ok(api, 'holding health module is exposed');
assert.equal(api.STORAGE_KEY, 'jei-holding-health-private-v2');

(async () => {
  const holding = api.normalizeHolding({ code: '2330', name: '台積電', cost: '100', shares: '1000', price: '110' });
  assert.deepEqual(JSON.parse(JSON.stringify(holding)), { code: '2330', name: '台積電', cost: 100, shares: 1000, price: 110 });
  assert.throws(() => api.normalizeHolding({ code: '<img>', cost: 100, shares: 1000 }), /股票代號/);
  assert.throws(() => api.normalizeHolding({ code: '2330', cost: 0, shares: 1000 }), /平均成本/);
  assert.throws(() => api.normalizeHolding({ code: '2330', cost: 100, shares: 1.5 }), /整數/);
  assert.equal(api.normalizeHolding({ code: '2330', cost: 100, shares: 1000, price: '' }).price, null);
  assert.throws(() => api.normalizeList([{ code:'2330',cost:100,shares:1 },{ code:'2330',cost:101,shares:1 }]), /重複/);

  const records = [holding, { code: '0050', cost: 150, shares: 10, price: '' }];
  const envelope = await api.encrypt(records, 'my-private-passphrase-2026', webcrypto);
  assert.equal(envelope.version, 2);
  assert.equal(JSON.stringify(envelope).includes('2330'), false, 'encrypted envelope must not expose stock codes');
  assert.equal(JSON.stringify(envelope).includes('台積電'), false, 'encrypted envelope must not expose stock names');
  assert.equal(JSON.stringify(envelope).includes('"shares":1000'), false, 'encrypted envelope must not expose the shares field');
  assert.deepEqual(JSON.parse(JSON.stringify(await api.decrypt(envelope, 'my-private-passphrase-2026', webcrypto))), JSON.parse(JSON.stringify(records.map(api.normalizeHolding))));
  await assert.rejects(() => api.decrypt(envelope, 'wrong-passphrase-0000', webcrypto));
  await assert.rejects(() => api.encrypt(records, 'short', webcrypto), /12 個字元/);

  const totals = api.summarize(records);
  assert.equal(totals.cost, 101500);
  assert.equal(totals.marketValue, 110000);
  assert.equal(totals.pnl, 10000);
  assert.equal(totals.pricedCount, 1);
  assert.match(html, /訪客版不顯示個人持股/);
  assert.match(html, /本機瀏覽器/);
  assert.match(html, /從本機匯入 JSON/);
  assert.match(source, /textContent/);
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|sendBeacon/);
  console.log('PASS private holdings are encrypted at rest, passphrase protected, local JSON import only, no upload path');
})().catch(error => { console.error(error); process.exitCode = 1; });
