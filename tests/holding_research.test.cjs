const assert = require('node:assert/strict');
const fs = require('node:fs');
const research = require('../remote/holding-research.js');

assert.deepEqual(research.freshness('2026-10-22', '2026-10-23'), { state: 'dated', ageDays: 1 });
assert.equal(research.freshness('2026-10-01', '2026-10-23').state, 'stale');
assert.equal(research.freshness('2026-10-24', '2026-10-23').state, 'unverified');
assert.equal(research.validDay('2026-02-30'), false);

const snapshot = research.marketSnapshot({ data_date: '2026-10-22', market: { status: '收盤' }, risk: { score: 68, reasons: ['breadth'], institutional_net_lots: -120 } },
  { morning: { us_market: [{ name: 'NASDAQ', date: '2026-10-22', change_pct: -2.6 }] } }, '2026-10-23');
assert.equal(snapshot.freshness.state, 'dated');
assert.equal(snapshot.usFreshness.state, 'dated');
assert.match(snapshot.linkage, /風險背景/);
assert.equal(research.marketSnapshot({}, null, '2026-10-23').freshness.state, 'unverified');
const stock = research.lookupStock({ data_date: '2026-10-22', universe: [{ code: '2330', name: '台積電' }], attack: [{ code: '2330', name: '台積電', score: 80, price: 1500, change_pct: 2 }], stock_sectors: { '2330': '半導體' }, sectors: [{ name: '半導體', score: 77 }], institutional: { '2330': { total: 1000, source: 'TWSE T86' } } }, '2330', '2026-10-23');
assert.equal(stock.ok, true);
assert.equal(stock.name, '台積電');
assert.equal(stock.candidate.price, 1500);
assert.equal(stock.sectorScore, 77);
assert.equal(stock.institutional.snapshotDate, '2026-10-22');
assert.equal(research.lookupStock({}, '2330', '2026-10-23').freshness.state, 'unverified');
assert.equal(research.lookupStock({}, '<img>', '2026-10-23').ok, false);

const plan = research.scenario({ price: 100, bull: 120, baseLow: 95, baseHigh: 105, bear: 90 });
assert.equal(plan.ok, true);
assert.equal(plan.moves.bull, 20);
assert.equal(plan.moves.bear, -10);
assert.equal(research.scenario({ price: 100, bull: 90, baseLow: 95, baseHigh: 105, bear: 80 }).ok, false);
assert.equal(research.scenario({ price: 100, bull: 120, baseLow: 95, baseHigh: 105, bear: 90 }).message.includes('假設'), true);

const trades = research.parseJournal('2026-10-01,2330,100,110,10\n2026-10-02,2330,100,90,10\ninvalid');
const stats = research.journalStats(trades);
assert.equal(stats.count, 2);
assert.equal(stats.wins, 1);
assert.equal(stats.winRate, 50);
assert.equal(stats.avgWin, 100);
assert.equal(stats.avgLoss, 100);
assert.equal(stats.profitFactor, 1);
assert.equal(stats.maxDrawdown, 100);
assert.equal(research.journalStats([{ date: 'bad', code: 'x', entry: 1, exit: 2, shares: 1 }]).count, 0);

const source = fs.readFileSync('remote/holding-research.js', 'utf8');
assert.doesNotMatch(source, /localStorage|sessionStorage|sendBeacon|XMLHttpRequest/);
assert.match(source, /fetcher\('\.\/system\.json'/);
const elements = new Map();
const fakeDocument = { getElementById(id) { if (!elements.has(id)) elements.set(id, { value: '', textContent: '', addEventListener() {} }); return elements.get(id); }, querySelectorAll() { return []; } };
assert.doesNotThrow(() => research.init(fakeDocument, null), 'research page initializes without relying on a closed-over browser root');
console.log('PASS dated market context, scenario validation, in-memory journal metrics and private-data boundaries');
