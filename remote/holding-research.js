/* Private-page research helpers. Calculations and notes stay in memory; network reads are limited to public JEI feeds. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.JEIHoldingResearch = api;
  if (typeof document !== 'undefined') api.init(document, root.fetch && root.fetch.bind(root));
}(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const validDay = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(Date.parse(value + 'T00:00:00Z')).toISOString().slice(0, 10) === value;
  function dayInTaipei(now) {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now || new Date());
    return ['year', 'month', 'day'].map(key => parts.find(part => part.type === key)?.value).join('-');
  }
  function freshness(asOf, today, maxAgeDays) {
    if (!validDay(asOf) || !validDay(today) || asOf > today) return { state: 'unverified', ageDays: null };
    const ageDays = Math.floor((Date.parse(today + 'T00:00:00Z') - Date.parse(asOf + 'T00:00:00Z')) / 86400000);
    return { state: ageDays > (Number.isSafeInteger(maxAgeDays) ? maxAgeDays : 4) ? 'stale' : 'dated', ageDays };
  }
  function marketSnapshot(system, brief, today) {
    const date = system && system.data_date;
    const fresh = freshness(date, today);
    const risk = system && system.risk || {};
    const market = system && system.market || {};
    const indices = brief && brief.morning && Array.isArray(brief.morning.us_market) ? brief.morning.us_market : [];
    const latestUS = indices.map(x => x.date).filter(validDay).sort().pop() || null;
    const usFresh = freshness(latestUS, today);
    const nasdaq = indices.find(x => /nasdaq/i.test(x.name || ''));
    let linkage = '資料不足，無法判斷美股對台股的短線方向';
    if (usFresh.state === 'dated' && nasdaq && Number.isFinite(Number(nasdaq.change_pct))) {
      linkage = Number(nasdaq.change_pct) <= -2 ? 'NASDAQ 明顯走弱；對台灣科技供應鏈構成風險背景，仍須看台股自身成交與族群確認' :
        Number(nasdaq.change_pct) >= 2 ? 'NASDAQ 明顯走強；科技風險偏好改善，但不能直接推論台股個股上漲' :
          'NASDAQ 變動未達 ±2% 的粗略警示門檻；不代表台股沒有其他國際風險';
    }
    return { date, freshness: fresh, status: market.status || '未知', risk: Number.isFinite(Number(risk.score)) ? Number(risk.score) : null,
      reasons: Array.isArray(risk.reasons) ? risk.reasons.slice(0, 5) : [], usDate: latestUS, usFreshness: usFresh,
      indices: indices.filter(x => x && typeof x.name === 'string' && Number.isFinite(Number(x.change_pct))), linkage };
  }
  function lookupStock(system, code, today) {
    const ticker = String(code || '').trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) return { ok: false, message: '請輸入有效股票代號。' };
    const stamp = system && system.data_date;
    const fresh = freshness(stamp, today);
    const groups = ['attack', 'next', 'monster', 'tomorrow_monster', 'future_monster'];
    const matches = groups.flatMap(group => (Array.isArray(system && system[group]) ? system[group] : []).map((item, index) => ({ group, index: index + 1, item })).filter(x => String(x.item.code).toUpperCase() === ticker));
    const candidate = matches.find(x => Number.isFinite(Number(x.item.price))) || matches[0];
    const name = candidate && candidate.item.name || (system && Array.isArray(system.universe) ? (system.universe.find(x => String(x.code).toUpperCase() === ticker) || {}).name : '') || ticker;
    const sector = system && system.stock_sectors && system.stock_sectors[ticker] || candidate && candidate.item.sector || null;
    const sectorState = sector && Array.isArray(system.sectors) ? system.sectors.find(x => x.name === sector) : null;
    const institutional = system && system.institutional && system.institutional[ticker];
    return { ok: true, code: ticker, name, date: stamp, freshness: fresh, candidate: candidate ? { category: candidate.group, rank: candidate.index,
      price: Number.isFinite(Number(candidate.item.price)) ? Number(candidate.item.price) : null,
      changePct: Number.isFinite(Number(candidate.item.change_pct)) ? Number(candidate.item.change_pct) : null,
      score: Number.isFinite(Number(candidate.item.score)) ? Number(candidate.item.score) : null } : null,
      sector: sector || null, sectorScore: sectorState && Number.isFinite(Number(sectorState.score)) ? Number(sectorState.score) : null,
      institutional: institutional && Number.isFinite(Number(institutional.total)) ? { total: Number(institutional.total), source: institutional.source || '未標示來源', snapshotDate: stamp } : null,
      message: fresh.state === 'dated' ? null : '資料日期過期或無法驗證；不提供即時個股結論。' };
  }
  function lookupFreeEvidence(feed, code, today) {
    const ticker = String(code || '').trim().toUpperCase();
    if (!feed || feed.schemaVersion !== 1 || !/^[A-Z0-9.-]{1,12}$/.test(ticker)) return null;
    const market = feed.markets && (feed.markets.listed && feed.markets.listed[ticker] ? 'listed' : feed.markets.otc && feed.markets.otc[ticker] ? 'otc' : null);
    if (!market) return { market: null, revenue: null, margin: null, valuation: null, status: '免費官方 feed 未收錄此代號，請先確認股票市場別。' };
    const record = feed.markets[market][ticker];
    const revenue = record.revenue || null;
    const margin = record.margin || null;
    const valuation = record.valuation || null;
    const financials = record.financials || null;
    const revenueFreshness = freshness(revenue && revenue.publishedAt, today, 45);
    const financialFreshness = freshness(financials && financials.publishedAt, today, 150);
    const marginFreshness = freshness(margin && margin.marketDate, today);
    const valuationFreshness = freshness(valuation && valuation.marketDate, today);
    return { market, revenue, margin, valuation, financials, revenueFreshness, financialFreshness, marginFreshness, valuationFreshness,
      sources: feed.sources || {}, generatedAt: feed.generatedAt || null,
      status: !revenue && !margin && !valuation ? '官方免費資料尚未提供此股可用欄位。' : null };
  }
  function scenario(input) {
    const values = ['price', 'bull', 'baseLow', 'baseHigh', 'bear'].map(key => Number(input && input[key]));
    if (values.some(value => !Number.isFinite(value) || value <= 0)) return { ok: false, message: '請填入五個大於 0 的價格。' };
    const [price, bull, low, high, bear] = values;
    if (!(bear < low && low <= high && high < bull)) return { ok: false, message: '價格順序須為：跌破失效價 < 震盪區間 < 續強觀察價。' };
    const pct = value => Math.round((value / price - 1) * 10000) / 100;
    return { ok: true, moves: { bull: pct(bull), baseLow: pct(low), baseHigh: pct(high), bear: pct(bear) },
      message: `續強觀察 ${bull}（${pct(bull)}%）｜震盪 ${low}–${high}（${pct(low)}% 至 ${pct(high)}%）｜跌破失效 ${bear}（${pct(bear)}%）。僅為使用者情境假設。` };
  }
  function journalStats(rows) {
    const valid = (Array.isArray(rows) ? rows : []).filter(row => row && validDay(row.date) && /^[A-Z0-9.-]{1,12}$/i.test(String(row.code || '')) &&
      Number.isFinite(Number(row.entry)) && Number(row.entry) > 0 && Number.isFinite(Number(row.exit)) && Number(row.exit) > 0 &&
      Number.isSafeInteger(Number(row.shares)) && Number(row.shares) > 0).map(row => ({ ...row, pnl: (Number(row.exit) - Number(row.entry)) * Number(row.shares) }))
      .sort((a, b) => a.date.localeCompare(b.date));
    if (!valid.length) return { count: 0, wins: 0, winRate: null, avgWin: null, avgLoss: null, profitFactor: null, maxDrawdown: 0 };
    const wins = valid.filter(row => row.pnl > 0), losses = valid.filter(row => row.pnl < 0);
    let equity = 0, peak = 0, maxDrawdown = 0;
    valid.forEach(row => { equity += row.pnl; peak = Math.max(peak, equity); maxDrawdown = Math.max(maxDrawdown, peak - equity); });
    const positive = wins.reduce((sum, row) => sum + row.pnl, 0), negative = Math.abs(losses.reduce((sum, row) => sum + row.pnl, 0));
    return { count: valid.length, wins: wins.length, winRate: wins.length / valid.length * 100,
      avgWin: wins.length ? positive / wins.length : null, avgLoss: losses.length ? negative / losses.length : null,
      profitFactor: negative ? positive / negative : (positive ? Infinity : null), maxDrawdown };
  }
  function parseJournal(text) {
    return String(text || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
      const [date, code, entry, exit, shares] = line.split(/[,，]/).map(part => part.trim());
      return { date, code, entry: Number(entry), exit: Number(exit), shares: Number(shares) };
    });
  }
  function sourceQueries(directory, code, market = null) {
    const ticker = String(code || '').trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) return [];
    const entries = directory && directory.schemaVersion === 1 && Array.isArray(directory.sources) ? directory.sources : [];
    return entries.filter(item => item && typeof item.name === 'string' && typeof item.url === 'string')
      .map(item => {
        const template = typeof item.search === 'string' ? item.search : item.url;
        const exchange = market === 'otc' ? 'TWO' : 'TW';
        const href = template.replaceAll('{ticker}', encodeURIComponent(ticker)).replaceAll('{market}', exchange);
        try {
          const parsed = new URL(href);
          if (parsed.protocol !== 'https:') return null;
          return { name: item.name, category: item.category || '其他來源', access: item.access || '請確認原站條件', evidence: item.evidence || '', href: parsed.href };
        } catch (_) { return null; }
      }).filter(Boolean);
  }
  function init(doc, fetcher) {
    const set = (id, text) => { const el = doc.getElementById(id); if (el) el.textContent = text; };
    const clearEphemeral = () => {
      ['financialEvidence', 'peerEvidence', 'catalystFact', 'catalystInference', 'catalystRumor', 'scenarioPrice', 'scenarioBull', 'scenarioBaseLow', 'scenarioBaseHigh', 'scenarioBear', 'tradeJournal', 'dailyConstraints', 'researchTicker'].forEach(id => {
        const el = doc.getElementById(id); if (el) el.value = '';
      });
      doc.querySelectorAll('.checklist input[type="checkbox"]').forEach(el => { el.checked = false; });
      ['financialStatus', 'scenarioResult', 'journalResult', 'researchTickerResult'].forEach(id => set(id, '研究暫存已清除。'));
      set('catalystFact', '');
    };
    const lock = doc.getElementById('lockHoldings');
    if (lock) lock.addEventListener('click', clearEphemeral);
    const globalTarget = typeof window !== 'undefined' ? window : globalThis;
    if (globalTarget && globalTarget.addEventListener) globalTarget.addEventListener('pagehide', clearEphemeral);
    let latestSystem = null, latestFree = null, latestSources = null;
    if (fetcher) Promise.allSettled([fetcher('./system.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw Error('market'); return r.json(); }),
      fetcher('./brief.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw Error('brief'); return r.json(); }),
      fetcher('./free_research.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw Error('free research'); return r.json(); }),
      fetcher('./research_source_directory.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw Error('research source directory'); return r.json(); })]).then(results => {
      const system = results[0].status === 'fulfilled' ? results[0].value : null;
      const brief = results[1].status === 'fulfilled' ? results[1].value : null;
      latestFree = results[2].status === 'fulfilled' ? results[2].value : null;
      latestSources = results[3].status === 'fulfilled' ? results[3].value : null;
      if (!system) { set('researchMarketStatus', '公開市場 feed 讀取失敗；暫停市場即時判讀。'); return; }
      latestSystem = system;
      const snapshot = marketSnapshot(system, brief, dayInTaipei());
      const stale = snapshot.freshness.state !== 'dated';
      set('researchMarketStatus', `${stale ? '⚠ 資料過期或日期未驗證，停止即時判讀' : '已核對日期的官方收盤參考'}｜台股資料日 ${snapshot.date || '未知'}｜${snapshot.status}｜市場風險 ${snapshot.risk ?? '缺值'}/100`);
      set('researchMarket', snapshot.reasons.length ? snapshot.reasons.join('｜') : '風險理由缺值；不補造資料。');
      const usText = snapshot.indices.length ? snapshot.indices.map(item => `${item.name} ${item.date} 收盤變動 ${Number(item.change_pct) > 0 ? '+' : ''}${item.change_pct}%`).join('｜') : '美股指數資料缺值。';
      set('researchGlobal', `${snapshot.usFreshness.state === 'dated' ? '美股有日期參考' : '美股資料過期／未驗證'}｜${usText}｜${snapshot.linkage}`);
      const articles = brief && brief.morning && Array.isArray(brief.morning.news) ? brief.morning.news.slice(0, 3) : [];
      set('researchNews', articles.length ? `國際／市場新聞摘要（標題未經 JEI 逐篇查證，不等於事件因果）：${articles.map(item => `${item.title || '未命名'}｜${item.source || '來源未知'}｜${item.published_at || '日期未知'}`).join('；')}` : '新聞摘要缺值，請查閱公司公告與原始國際來源。');
      const risk = system.risk || {};
      const flowText = [risk.institutional_net_lots != null ? `市場法人淨額 ${risk.institutional_net_lots} 股` : '', risk.institutional_sell_ratio != null ? `賣超家數比 ${risk.institutional_sell_ratio}%` : ''].filter(Boolean).join('｜');
      set('researchFlow', `${flowText || '法人資料缺值'}｜資料日 ${system.data_date || '未知'}；此為市場彙總，不等於個股法人，也不含融資券與大戶持股分布。`);
      const freeCount = latestFree && latestFree.markets ? Object.keys(latestFree.markets.listed || {}).length + Object.keys(latestFree.markets.otc || {}).length : 0;
      set('researchFreeStatus', latestFree ? `免費官方資料已同步｜${freeCount} 檔上市櫃｜更新 ${latestFree.generatedAt || '日期未知'}｜官方資料源日期以個股欄位為準。` : '免費官方財務 feed 尚未同步；此區不會改以付費或不明來源代替。');
    });
    const tickerButton = doc.getElementById('researchTickerRun');
    if (tickerButton) tickerButton.addEventListener('click', () => {
      if (!latestSystem) { set('researchTickerResult', '公開 feed 尚未完成同步；暫不分析。'); return; }
      const found = lookupStock(latestSystem, doc.getElementById('researchTicker').value, dayInTaipei());
      if (!found.ok) { set('researchTickerResult', found.message); return; }
      const evidence = lookupFreeEvidence(latestFree, found.code, dayInTaipei());
      const sourceContainer = doc.getElementById('researchSourceLinks');
      if (sourceContainer) {
        sourceContainer.replaceChildren();
        const links = sourceQueries(latestSources, found.code, evidence && evidence.market);
        if (!links.length) sourceContainer.textContent = '多來源目錄尚未載入；請稍後重試。';
        else links.forEach(item => {
          const card = doc.createElement('p');
          const link = doc.createElement('a');
          link.href = item.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `${item.category}｜${item.name} ↗`;
          const detail = doc.createElement('small'); detail.textContent = ` ${item.access}${item.evidence ? `。${item.evidence}` : ''}`;
          card.append(link, doc.createElement('br'), detail); sourceContainer.append(card);
        });
      }
      const parts = [`${found.code} ${found.name}`, `JEI 快照資料日 ${found.date || '未知'}`, found.freshness.state === 'dated' ? '日期可用' : found.message || '日期待驗證', '非券商即時報價，不能視為下單訊號'];
      if (found.candidate) parts.push(`候選：${found.candidate.category} #${found.candidate.rank}｜模型分數 ${found.candidate.score ?? '缺值'}｜價格 ${found.candidate.price ?? '缺值'}${found.candidate.changePct == null ? '' : `｜漲跌 ${found.candidate.changePct}%`}`);
      else parts.push('今日公開候選清單未收錄；不代表基本面或投資價值判定。');
      parts.push(`族群 ${found.sector || '未分類'}｜族群分數 ${found.sectorScore ?? '缺值'}`);
      parts.push(found.institutional ? `三大法人淨額 ${found.institutional.total} 股｜${found.institutional.source}｜系統快照 ${found.institutional.snapshotDate}（來源公告日未獨立提供）` : '個股法人資料缺值');
      if (evidence && evidence.status) parts.push(evidence.status);
      if (evidence && evidence.revenue) {
        const item = evidence.revenue, dated = evidence.revenueFreshness.state === 'dated' ? '' : `（資料過期／日期未驗證 ${item.publishedAt || '未知'}）`;
        parts.push(`月營收 ${item.period || '期間未知'}｜年增 ${item.monthlyYoYPct == null ? '缺值' : `${item.monthlyYoYPct}%`}｜累計年增 ${item.cumulativeYoYPct == null ? '缺值' : `${item.cumulativeYoYPct}%`}｜官方公告 ${item.publishedAt || '日期未知'}${dated}`);
      }
      if (evidence && evidence.financials) {
        const item = evidence.financials, dated = evidence.financialFreshness.state === 'dated' ? '' : '（財報資料過期／日期未驗證）';
        parts.push(`一般產業財報 ${item.period || '季度未知'}｜毛利率 ${item.grossMarginPct == null ? '缺值' : `${item.grossMarginPct}%`}｜營益率 ${item.operatingMarginPct == null ? '缺值' : `${item.operatingMarginPct}%`}｜母公司淨利率 ${item.parentNetMarginPct == null ? '缺值' : `${item.parentNetMarginPct}%`}｜EPS ${item.eps ?? '缺值'}｜負債比 ${item.debtRatioPct == null ? '缺值' : `${item.debtRatioPct}%`}｜流動比 ${item.currentRatioPct == null ? '缺值' : `${item.currentRatioPct}%`}｜每股淨值 ${item.bookValuePerShare ?? '缺值'}｜公告 ${item.publishedAt || '日期未知'}${dated}`);
      }
      if (evidence && evidence.margin) {
        const item = evidence.margin;
        parts.push(`融資餘額 ${item.marginBuyBalance ?? '缺值'}｜日增減 ${item.marginBuyChange ?? '缺值'}｜融券餘額 ${item.marginShortBalance ?? '缺值'}｜融資使用率 ${item.marginUsagePct == null ? '缺值' : `${item.marginUsagePct}%`}｜資料日 ${item.marketDate || '未知'}${evidence.marginFreshness.state === 'dated' ? '' : '（過期／未驗證）'}`);
        if (item.sblShortBalance != null) parts.push(`借券賣出餘額 ${item.sblShortBalance}｜借券資料日 ${item.marketDate || '未知'}`);
      }
      if (evidence && evidence.valuation) {
        const item = evidence.valuation;
        parts.push(`官方估值快照 ${item.marketDate || '日期未知'}｜本益比 ${item.pe ?? '缺值'}｜殖利率 ${item.dividendYieldPct == null ? '缺值' : `${item.dividendYieldPct}%`}｜股價淨值比 ${item.pb ?? '缺值'}${evidence.valuationFreshness.state === 'dated' ? '' : '（過期／未驗證）'}`);
      }
      parts.push('這些免費指標是研究線索，不是品質評分或買賣訊號；跨產業財報口徑、現金流、同業比較、大戶持股變化與券商目標價仍須依官方公告逐項核對。');
      set('researchTickerResult', parts.join('｜'));
    });
    const scenarioButton = doc.getElementById('scenarioRun');
    if (scenarioButton) scenarioButton.addEventListener('click', () => {
      const number = id => { const value = doc.getElementById(id).value; return value === '' ? NaN : Number(value); };
      set('scenarioResult', scenario({ price: number('scenarioPrice'), bull: number('scenarioBull'), baseLow: number('scenarioBaseLow'), baseHigh: number('scenarioBaseHigh'), bear: number('scenarioBear') }).message);
    });
    const journalButton = doc.getElementById('journalRun');
    if (journalButton) journalButton.addEventListener('click', () => {
      const stats = journalStats(parseJournal(doc.getElementById('tradeJournal').value));
      const fmt = value => value == null ? '—' : Number.isFinite(value) ? Math.round(value * 100) / 100 : '無虧損樣本';
      set('journalResult', stats.count ? `${stats.count} 筆有效交易｜毛勝率 ${fmt(stats.winRate)}%｜平均獲利 ${fmt(stats.avgWin)}｜平均虧損 ${fmt(stats.avgLoss)}｜毛獲利因子 ${fmt(stats.profitFactor)}｜累積序列最大回撤 ${fmt(stats.maxDrawdown)}。未扣費稅，樣本不代表未來。` : '沒有有效交易資料；請使用日期,代號,進場價,出場價,股數格式。');
    });
    ['financialEvidence', 'peerEvidence'].forEach(id => {
      const el = doc.getElementById(id), output = id === 'financialEvidence' ? 'financialStatus' : null;
      if (el && output) el.addEventListener('input', () => set(output, el.value.trim() ? '已輸入手動研究線索；請自行核對原始公告，系統尚未驗證來源。' : '尚未輸入查證資料。'));
    });
  }
  return Object.freeze({ validDay, dayInTaipei, freshness, marketSnapshot, lookupStock, lookupFreeEvidence, scenario, journalStats, parseJournal, sourceQueries, init });
}));
