const assert = require('node:assert/strict');
const fs = require('node:fs');
const research = require('../remote/holding-research.js');

assert.deepEqual(research.freshness('2026-10-22', '2026-10-23'), { state: 'dated', ageDays: 1 });
assert.equal(research.freshness('2026-10-01', '2026-10-23').state, 'stale');
assert.equal(research.freshness('2026-09-10', '2026-10-23', 45).state, 'dated');
assert.equal(research.freshness('2026-08-01', '2026-10-23', 45).state, 'stale');
assert.equal(research.freshness('2026-10-24', '2026-10-23').state, 'unverified');
assert.equal(research.validDay('2026-02-30'), false);

const sourceDirectory = JSON.parse(fs.readFileSync(require.resolve('../remote/research_source_directory.json'), 'utf8'));
const sourceLinks = research.sourceQueries(sourceDirectory, '2330');
assert.ok(sourceLinks.length >= 10, 'research view should expose multiple independent source categories');
assert.ok(sourceLinks.some(item => item.name.includes('第一金')));
assert.ok(sourceLinks.some(item => item.name.includes('華南永昌')));
assert.ok(sourceLinks.some(item => item.name.includes('元大')));
assert.ok(sourceLinks.some(item => item.name.includes('XQ 全球贏家')));
assert.ok(sourceLinks.some(item => item.name.includes('AI 智慧產業地圖') && item.category.includes('交叉查證')));
assert.ok(sourceLinks.some(item => item.name.includes('籌碼K線')));
assert.ok(sourceLinks.some(item => item.name.includes('PChome') && item.category.includes('選股')));
assert.ok(sourceLinks.some(item => item.name.includes('Cocoboomboom') && item.category.includes('Podcast')));
assert.ok(sourceLinks.some(item => item.name.includes('SoundOn') && item.category.includes('Podcast')));
assert.ok(sourceLinks.some(item => item.category === '論壇線索'));
assert.ok(sourceLinks.every(item => new URL(item.href).protocol === 'https:'));
assert.deepEqual(research.sourceQueries(sourceDirectory, '<script>'), [], 'invalid ticker must not form external search links');
assert.equal(sourceLinks.find(item => item.name.includes('PTT')).href.includes('2330'), true);
assert.match(sourceLinks.find(item => item.name.includes('Yahoo')).href,/2330\.TW\/news$/);
assert.match(research.sourceQueries(sourceDirectory, '6488', 'otc').find(item => item.name.includes('Yahoo')).href,/6488\.TWO\/news$/);

const snapshot = research.marketSnapshot({ data_date: '2026-10-22', market: { status: '收盤' }, risk: { score: 68, reasons: ['breadth'], institutional_net_lots: -120 } },
  { morning: { us_market: [{ name: 'NASDAQ', date: '2026-10-22', change_pct: -2.6 }] } }, '2026-10-23');
assert.equal(snapshot.freshness.state, 'dated');
assert.equal(snapshot.usFreshness.state, 'dated');
const crossMarketSnapshot = research.marketSnapshot({ data_date: '2026-10-22', market: { status: '收盤' }, risk: {} },
  { morning: { us_market: [{ name: 'NASDAQ', date: '2026-10-22', change_pct: -2.6 }],
    global_market: [{ name: '費城半導體', date: '2026-10-23', change_pct: 0.44 }, { name: 'WTI 原油', date: '2026-10-23', change_pct: 3.82 }] } }, '2026-10-24');
assert.equal(crossMarketSnapshot.usDate, '2026-10-22', 'global quote dates must not make the US core freshness look newer');
assert.equal(crossMarketSnapshot.indices.length, 3, 'cross-market context should render beside the three core US indexes');
assert.equal(crossMarketSnapshot.indices[1].name, '費城半導體');
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
const freeEvidence = research.lookupFreeEvidence({ schemaVersion: 1, generatedAt: '2026-10-23T00:00:00Z', sources: { revenue: 'official' }, markets: {
  listed: { '2330': { revenue: { publishedAt: '2026-10-17', period: '2026-09-01', monthlyYoYPct: 20 }, margin: { marketDate: '2026-10-22', marginBuyBalance: 100, marginBuyChange: 5 }, valuation: { marketDate: '2026-10-22', pe: 21 } } }, otc: {}
} }, '2330', '2026-10-23');
assert.equal(freeEvidence.market, 'listed');
assert.equal(freeEvidence.revenueFreshness.state, 'dated');
assert.equal(freeEvidence.margin.marginBuyChange, 5);
assert.equal(research.lookupFreeEvidence(null, '2330', '2026-10-23'), null);
assert.equal(research.lookupFreeEvidence({ schemaVersion: 1, markets: { listed: {}, otc: {} } }, '2330', '2026-10-23').market, null);
const briefRows = research.buildResearchBrief(stock, freeEvidence, snapshot, [{ title: '市場消息', source: '測試來源', published_at: '2026-10-22' }]);
assert.equal(briefRows.length, 8, 'ticker report should provide the eight research checkpoints');
assert.ok(briefRows.every(row => row.title && row.status && row.source && row.asOf && row.detail), 'every checkpoint should expose status, provenance and date');
assert.match(briefRows[1].detail, /風險背景/);
assert.match(briefRows[7].detail, /待查線索/);
const missingBrief = research.buildResearchBrief(research.lookupStock({}, '2330', '2026-10-23'), null, research.marketSnapshot({}, null, '2026-10-23'));
assert.ok(missingBrief.every(row => /缺值|未驗證/.test(row.status)), 'missing feeds must remain explicit and never turn into a fabricated conclusion');
const renderedRows = [];
const statusTarget = { replaceChildren() { renderedRows.length = 0; }, append(row) { renderedRows.push(row); } };
const fakeTableDocument = { createElement() { return { append() {}, textContent: '' }; } };
research.renderSourceStatus(fakeTableDocument, statusTarget, snapshot, null);
assert.equal(renderedRows.length, 13, 'source status should include connected, manual-only and unavailable datasets');
const watchStatus = { textContent: '' }, renderedEpisodes = [];
const episodeContainer = { replaceChildren() { renderedEpisodes.length = 0; }, append(item) { renderedEpisodes.push(item); }, set textContent(value) { this.message = value; } };
const dom = { createElement(tag) { return { tag, children: [], append(...items) { this.children.push(...items); }, textContent: '', href: '' }; } };
const watchState = research.renderGooayeWatch(dom, watchStatus, episodeContainer, {
  schemaVersion: 1, checkedAt: '2026-10-25T01:00:00Z', latestPublishedAt: '2026-10-24',
  summaryPage: { lastUpdated: '2026-06-29', checked: true },
  episodes: [{ title: 'EP708 | 測試標題', episode: 'EP708', publishedAt: '2026-10-24', url: 'https://player.soundon.fm/p/ep708' },
    { title: 'unsafe', episode: 'EP707', publishedAt: '2026-10-23', url: 'javascript:alert(1)' }]
}, '2026-10-25');
assert.equal(watchState.summaryFreshness.state, 'stale');
assert.match(watchStatus.textContent, /摘要頁已過期/);
assert.equal(renderedEpisodes.length, 2);
assert.match(renderedEpisodes[0].children[0].href, /^https:\/\//);
assert.equal(renderedEpisodes[1].children[0].href, '', 'non-HTTPS episode links must not be rendered as active links');

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
assert.match(fs.readFileSync('remote/holding-health.html', 'utf8'), /researchSourceStatus/);
assert.match(fs.readFileSync('remote/holding-health.html', 'utf8'), /researchDailyBrief/);
const elements = new Map();
const fakeDocument = { getElementById(id) { if (!elements.has(id)) elements.set(id, { value: '', textContent: '', addEventListener() {} }); return elements.get(id); }, querySelectorAll() { return []; } };
assert.doesNotThrow(() => research.init(fakeDocument, null), 'research page initializes without relying on a closed-over browser root');
const newsElements = [];
const newsDoc = { createElement(tag) { const node = { tag, textContent: '', children: [], append(...items) { this.children.push(...items); }, setAttribute() {} }; newsElements.push(node); return node; } };
const newsStatus = { textContent: '' }, newsThemes = { children: [], replaceChildren() { this.children = []; }, append(node) { this.children.push(node); } };
const newsResult = research.renderDailyNewsWatch(newsDoc, newsStatus, newsThemes, {
  schemaVersion: 1, reportDate: '2026-10-24', checkedAt: '2026-10-25T09:15:00+08:00', storyCount: 8,
  categoryCounts: { 美股: 3 }, themes: [{ id: 'us_semiconductors', label: '美股／半導體連動', articleCount: 3, references: [
    { publisher: '工商時報', publishedAt: '10/24 06:00', url: 'https://example.com/article' },
    { publisher: '不安全來源', url: 'javascript:alert(1)' }
  ] }]
});
assert.equal(newsResult.ok, true);
assert.match(newsStatus.textContent, /2026-10-24.*8 則焦點/);
assert.equal(newsThemes.children.length, 1);
assert.equal(newsThemes.children[0].children.filter(node => node.tag === 'a').length, 1, 'news links are HTTPS only');
assert.equal(research.renderDailyNewsWatch(newsDoc, newsStatus, newsThemes, null).ok, false, 'missing news feed fails closed');
const videoRows = { children: [], replaceChildren() { this.children = []; }, append(node) { this.children.push(node); } };
const videoDir = { children: [], replaceChildren() { this.children = []; }, append(node) { this.children.push(node); } };
const videoStatus = { textContent: '' };
const videoResult = research.renderVideoUploadWatch(newsDoc, videoStatus, videoRows, videoDir, {
  schemaVersion: 1, sourceCount: 1, successfulSourceCount: 1, checkedAt: '2026-10-25T09:45:00+08:00',
  videos: [{ channel: 'M觀點', level: '中階', title: 'AI 市場觀察', publishedAt: '2026-10-24', url: 'https://www.youtube.com/watch?v=AbCdEf12345' }]
}, { channels: [{ name: 'M觀點', level: '中階', focus: '科技', url: 'https://www.youtube.com/@mviewpoint', verifiedOfficial: true }] });
assert.equal(videoResult.ok, true);
assert.equal(videoRows.children.length, 1);
assert.equal(videoDir.children.length, 1);
assert.match(videoStatus.textContent, /未讀影片內容/);
console.log('PASS dated market context, scenario validation, in-memory journal metrics and private-data boundaries');
