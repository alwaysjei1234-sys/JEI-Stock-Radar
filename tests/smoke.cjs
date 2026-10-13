const fs=require('node:fs');const assert=require('node:assert/strict');const html=fs.readFileSync('remote/index.html','utf8');const paper=fs.readFileSync('remote/paper.html','utf8');const py=fs.readFileSync('scripts/update_system.py','utf8');const manifest=fs.readFileSync('app/src/main/AndroidManifest.xml','utf8');const activity=fs.readFileSync('app/src/main/java/com/jei/stockradar/MainActivity.java','utf8');
let passed=0,failed=0;
function check(label,fn){try{fn();passed++;console.log('PASS',label)}catch(e){failed++;console.error('FAIL',label,e.stack||e.message);process.exitCode=1}}
check('Public page guards private routes',()=>{assert.match(html,/function go\(id\)\{if\(!JEI_PRIVATE_APP/);assert.match(html,/function loadHoldings\(\)\{if\(!JEI_PRIVATE_APP/)});
check('No public portfolio nodes removed (prevents JS null dereference)',()=>assert.doesNotMatch(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>el\.remove\(\)\)/));
check('Public feed strips private positions',()=>{assert.match(py,/if out\.get\("holdings"\):/);assert.match(html,/system\.holdings=JEI_PRIVATE_APP\?/)});
check('Android backups disabled',()=>assert.match(manifest,/android:allowBackup="false"/));
check('WebView file-origin crossing disabled',()=>{assert.match(activity,/setAllowFileAccessFromFileURLs\(false\)/);assert.match(activity,/setAllowUniversalAccessFromFileURLs\(false\)/)});
check('Stock screener and heatmap wired',()=>{assert.match(html,/function renderAttackScreener\(/);assert.match(html,/function renderSectorHeatmap\(/);assert.match(html,/renderSectors\(\);renderSectorHeatmap\(\)/)});
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(Boolean);const vm=require('node:vm');check('Inline JavaScript syntax',()=>{for(const code of scripts)new vm.Script(code)});

check('Trading hours use Asia/Taipei timezone',()=>assert.match(html,/function tradingWindow\(\).*timeZone:'Asia\/Taipei'/));
check('Screener updates freshness label',()=>assert.match(html,/function renderAttackScreener\(\)\{updateFeedFreshness\(\)/));
check('Private sections are hidden without removal',()=>assert.match(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>\{el\.style\.display='none'/));

check('WebView external links open outside app',()=>assert.ok(activity.includes('shouldOverrideUrlLoading')&&activity.includes('Intent.ACTION_VIEW')));
check('Mixed content blocked',()=>assert.ok(activity.includes('MIXED_CONTENT_NEVER_ALLOW')));

check('Sector dropdown is wired into stock screening',()=>assert.ok(html.includes('id="screenSector"')&&html.includes('function syncScreenSectors()')&&html.includes("'screenSector','screenOrder'")));

check('Ranking cards escape untrusted market fields',()=>assert.ok(html.includes('function escapeMarketText(value)')&&html.includes('safe(x.name)')&&html.includes('safe(x.reason||x.status)')));

check('Feed date uses timezone-safe calendar parts',()=>assert.ok(html.includes('function updateFeedFreshness()')&&html.includes('formatToParts(now)')&&html.includes('dp.year')));

check('Market text escaping blocks HTML injection at runtime',()=>{
 const line=html.split('\n').find(x=>x.startsWith('function escapeMarketText('));
 assert.ok(line,'escape helper missing');
 const ctx={};vm.runInNewContext(line+';globalThis.testEscape=escapeMarketText;',ctx);
 assert.equal(ctx.testEscape('<img src=x onerror="alert(1)">'),'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
 assert.equal(ctx.testEscape('A&B'), 'A&amp;B');
 assert.equal(ctx.testEscape(null),'');
});
check('Taiwan trading hours are timezone-independent at runtime',()=>{
 const line=html.split('\n').find(x=>x.startsWith('function tradingWindow('));
 assert.ok(line,'trading window helper missing');
 const ctx={Date:class extends Date{constructor(){super('2026-10-13T01:00:00Z')}} ,Intl};
 vm.runInNewContext(line+';globalThis.testTrading=tradingWindow;',ctx);
 assert.equal(ctx.testTrading(),true,'Tuesday 09:00 Taipei must be trading');
 ctx.Date=class extends Date{constructor(){super('2026-10-13T07:00:00Z')}};
 assert.equal(ctx.testTrading(),false,'Tuesday 15:00 Taipei must be closed');
 ctx.Date=class extends Date{constructor(){super('2026-10-17T01:00:00Z')}};
 assert.equal(ctx.testTrading(),false,'Saturday 09:00 Taipei must be closed');
});

check('Stock screener filters score, sector and stale market at runtime',()=>{
 const line=html.split('\n').find(x=>x.startsWith('function renderAttackScreener('));assert.ok(line);
 const els={screenScore:{value:'75'},screenQuery:{value:''},screenSector:{value:'AI'},screenOrder:{value:'score'},screenCount:{textContent:''}};
 let captured=[];const ctx={system:{attack:[{code:'1111',score:90,sector:'AI'},{code:'2222',score:60,sector:'AI'},{code:'3333',score:95,sector:'航運'}],market:{mode:'收盤'},data_date:'2026-10-13'},$:id=>els[id],renderRank:(_id,arr)=>{captured=arr},updateFeedFreshness:()=>{},syncScreenSectors:()=>{}};
 vm.runInNewContext(line+';globalThis.testScreen=renderAttackScreener;',ctx);ctx.testScreen();assert.equal(captured.length,1);assert.equal(captured[0].code,'1111');
 ctx.system.market.mode='盤中資料不足';ctx.testScreen();assert.equal(captured.length,0);
});

check('Paper trading has no broker order submission',()=>{assert.ok(html.includes('href="./paper.html"'));assert.ok(paper.includes('jei-paper-trades-v1'));assert.doesNotMatch(paper,/JEINative\.|XMLHttpRequest|WebSocket|\/api\/orders|placeOrder\(/);assert.ok(paper.includes("fetch('./system.json?ts='"),'read-only feed fetch is allowed')});
check('Paper ledger JavaScript syntax',()=>{for(const match of paper.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(match[1])});
check('Paper PnL charges both-side fees and sell-side tax',()=>{
 const line=paper.split('\n').find(x=>x.startsWith('function calc('));assert.ok(line);
 const ctx={};vm.runInNewContext(line+';globalThis.testCalc=calc;',ctx);
 const t={side:'long',entry:100,exit:110,qty:1000,fee:0.001425,tax:0.0015};
 const p=ctx.testCalc(t);assert.equal(p.gross,10000);assert.ok(Math.abs(p.fees-299.25)<1e-8);assert.equal(p.tax,165);assert.ok(Math.abs(p.net-9535.75)<1e-8);
 const short=ctx.testCalc({...t,side:'short'});assert.equal(short.gross,-10000);assert.equal(short.tax,150);
});

check('Paper scanner is read-only and halts on insufficient market coverage',()=>{assert.ok(paper.includes("fetch('./system.json?ts='"));assert.ok(paper.includes("halted=feed.market?.mode==='盤中資料不足'"));assert.ok(paper.includes("if(halted||!valid)return"));assert.doesNotMatch(paper,/JEINative\.|\/api\/orders|placeOrder\(/)});
check('Paper open positions are isolated from realized trades',()=>{assert.ok(paper.includes("jei-paper-open-positions-v1"));assert.ok(paper.includes("function loadPositions()"));assert.ok(paper.includes("function renderPositions()"));assert.ok(paper.includes("const list=load(),p=list.map(calc)"))});


const cash=fs.readFileSync('remote/cash.html','utf8');
check('Cash simulation JavaScript parses',()=>{const script=cash.match(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/);assert.ok(script);new vm.Script(script[1])});
check('Cash and day-trading local records remain separate',()=>{assert.ok(cash.includes('jei-cash-trades-v1'));assert.ok(cash.includes('jei-cash-open-positions-v1'));assert.ok(cash.includes('jei-cash-auto-watch-v1'));assert.ok(!paper.includes('jei-cash-trades-v1'))});
check('Cash simulation uses standard 0.3 percent stock sell tax',()=>{assert.ok(cash.includes('現股交易稅率（賣出）'));assert.ok(cash.includes('value="0.003"'))});
check('Cash simulation enforces capital and per-position limit',()=>{assert.ok(cash.includes('function cashMetrics()'));assert.ok(cash.includes('cost>m.cfg.limit||cost>m.available'));assert.ok(cash.includes('jei-cash-account-config-v1'))});

check('Cash paper close records only confirmed realized trades',()=>{assert.ok(cash.includes("id=\"closeTrade\""));assert.ok(cash.includes("function renderClose()"));assert.ok(cash.includes("reason:"));assert.ok(cash.includes("savePositions(positions)"));assert.ok(cash.includes("oldHistory=localStorage.getItem(KEY)"))});
check('Cash paper performance uses realized net of fees and tax',()=>{assert.ok(cash.includes("100*m.closed/m.cfg.capital"));assert.ok(cash.includes("closed.filter(t=>calc(t).net>0)"));assert.ok(cash.includes("tax:0.003"))});


check('Cash momentum strategy archive sync is independent of current radar',()=>{assert.ok(cash.includes("daily_prices.json?ts="));assert.ok(cash.includes("async function syncDailyPrices()"));assert.ok(cash.includes("if(day<=t.day||day<=t.lastDay)continue"));assert.ok(cash.includes("if(t.strategies)strategyAdvance(t,price,day)"))});
check('Four cash exit strategies are present',()=>{assert.ok(cash.includes("id:'fixed5'"));assert.ok(cash.includes("id:'fixed7'"));assert.ok(cash.includes("id:'fixed10'"));assert.ok(cash.includes("id:'trailing'"))});

check('Intraday quotes cannot masquerade as official post-close',()=>{assert.ok(py.includes('if live_valid and market_open:'));assert.ok(py.includes('source_is_today=twse_today and tpex_today'));assert.ok(py.includes('if source_is_today and not market_open and now.hour >= 13:'))});

if(passed+failed<30){console.error('FAIL expected at least 30 independent checks');process.exitCode=1;}
console.log(`JEI smoke summary: ${passed}/${passed+failed} passed (${Math.round(100*passed/(passed+failed))}%)`);
