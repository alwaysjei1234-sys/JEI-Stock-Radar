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

check('Feed date uses timezone-safe calendar parts',()=>assert.ok(html.includes('function updateFeedFreshness()')&&html.includes('function taipeiDay()')&&html.includes('formatToParts(new Date())')&&html.includes('dp.year')));

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
 let captured=[];const ctx={system:{attack:[{code:'1111',score:90,sector:'AI'},{code:'2222',score:60,sector:'AI'},{code:'3333',score:95,sector:'航運'}],market:{mode:'收盤'},data_date:'2026-10-13'},$:id=>els[id],renderRank:(_id,arr)=>{captured=arr},updateFeedFreshness:()=>{},syncScreenSectors:()=>{},tradingWindow:()=>false,feedLiveFresh:()=>false};
 vm.runInNewContext(line+';globalThis.testScreen=renderAttackScreener;',ctx);ctx.testScreen();assert.equal(captured.length,1);assert.equal(captured[0].code,'1111');
 ctx.system.market.mode='盤中資料不足';ctx.testScreen();assert.equal(captured.length,0);
});

check('Paper trading is linked and has no broker order submission',()=>{assert.ok(html.includes('href="./paper.html"'));assert.ok(paper.includes('jei-paper-trades-v1'));assert.doesNotMatch(paper,/JEINative\.|\/api\/orders|placeOrder\(/)});
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
check('Cash simulation JavaScript parses',()=>{const script=cash.match(/<script>([\s\S]*?)<\/script>/);assert.ok(script);new vm.Script(script[1])});
check('Cash and day-trading local records remain separate',()=>{assert.ok(cash.includes('jei-cash-trades-v1'));assert.ok(cash.includes('jei-cash-open-positions-v1'));assert.ok(cash.includes('jei-cash-auto-watch-v1'));assert.ok(!paper.includes('jei-cash-trades-v1'))});
check('Cash simulation uses standard 0.3 percent stock sell tax',()=>{assert.ok(cash.includes('現股交易稅率（賣出）'));assert.ok(cash.includes('value="0.003"'))});
check('Cash simulation enforces capital and per-position limit',()=>{assert.ok(cash.includes('function cashMetrics()'));assert.ok(cash.includes('cost>m.cfg.limit||cost>m.available'));assert.ok(cash.includes('jei-cash-account-config-v1'))});

check('Cash paper close records only confirmed realized trades',()=>{assert.ok(cash.includes("id=\"closeTrade\""));assert.ok(cash.includes("function renderClose()"));assert.ok(cash.includes("reason:"));assert.ok(cash.includes("savePositions(positions)"));assert.ok(cash.includes("oldHistory=localStorage.getItem(KEY)"))});
check('Cash paper performance uses realized net of fees and tax',()=>{assert.ok(cash.includes("100*m.closed/m.cfg.capital"));assert.ok(cash.includes("closed.filter(t=>calc(t).net>0)"));assert.ok(cash.includes("tax:0.003"))});


check('Cash momentum strategy archive sync is independent of current radar',()=>{assert.ok(cash.includes("daily_prices.json?ts="));assert.ok(cash.includes("async function syncDailyPrices()"));assert.ok(cash.includes("if(day<=t.day||day<=t.lastDay)continue"));assert.ok(cash.includes("if(t.strategies)strategyAdvance(t,price,day)"))});
check('Four cash exit strategies are present',()=>{assert.ok(cash.includes("id:'fixed5'"));assert.ok(cash.includes("id:'fixed7'"));assert.ok(cash.includes("id:'fixed10'"));assert.ok(cash.includes("id:'trailing'"))});

const source=name=>{const start=html.indexOf('function '+name+'(');assert.ok(start>=0,name);const end=html.indexOf('\nfunction ',start+1);return html.slice(start,end<0?html.length:end)};
check('Offline and remote UI are identical',()=>assert.equal(fs.readFileSync('app/src/main/assets/index.html','utf8'),html));
check('Cold off-hours holdings obtain public close prices without exposing positions',()=>{
 const ctx={system:{holdings:{},quotes:{'2609':{name:'陽明',price:66,change_pct:10,data_date:'2026-10-12'},'00937B':{name:'ETF',price:15.5,change_pct:0,data_date:'2026-10-12'}}},market:{},tradingWindow:()=>false,renderHoldings:()=>{}};
 vm.runInNewContext(source('seedMarketFromSystem')+';seedMarketFromSystem()',ctx);
 assert.equal(ctx.market['2609'].price,66);assert.ok(Math.abs(ctx.market['2609'].prev-60)<1e-8);assert.equal(ctx.market['00937B'].price,15.5);assert.equal(ctx.market['2609'].live,false);assert.equal(Object.keys(ctx.system.holdings).length,0);
});
check('Private ETF codes are included even with a full market universe',()=>{
 const ctx={holdings:[{code:'00937B'}],system:{universe:Array.from({length:501},(_,i)=>({code:String(1000+i)}))}};
 vm.runInNewContext(source('liveCodes')+';globalThis.codes=liveCodes()',ctx);assert.ok(ctx.codes.includes('00937B'));assert.equal(ctx.codes.length,502);
});
check('Feed freshness rejects yesterday, expired and future timestamps',()=>{
 const instant=Date.parse('2026-10-13T01:10:00Z');const FakeDate=class extends Date{constructor(...args){super(...(args.length?args:[instant]))}static now(){return instant}};
 const ctx={Date:FakeDate,Intl,system:{data_date:'2026-10-13',updated_at:'2026-10-13 09:05',market:{live_valid:true,stale:false}}};
 vm.runInNewContext(source('taipeiDay')+'\n'+source('feedLiveFresh')+';globalThis.fresh=feedLiveFresh',ctx);
 assert.equal(ctx.fresh(),true);ctx.system.data_date='2026-10-12';assert.equal(ctx.fresh(),false);ctx.system.data_date='2026-10-13';ctx.system.updated_at='2026-10-13 08:00';assert.equal(ctx.fresh(),false);ctx.system.updated_at='2026-10-13 10:00';assert.equal(ctx.fresh(),false);
});
check('Partial live scan halts rankings instead of promoting 20 quotes',()=>{
 let rendered=false;const ctx={market:Object.fromEntries(Array.from({length:20},(_,i)=>[String(1000+i),{live:true,date:'2026-10-13',time:'09:00:00'}])),system:{universe:Array(1951),market:{}},Date:class extends Date{static now(){return Date.parse('2026-10-13T01:01:00Z')}},taipeiDay:()=> '2026-10-13',renderSystem:()=>{rendered=true}};
 vm.runInNewContext(source('haltLiveRanks')+'\n'+source('scanLiveUniverse')+';scanLiveUniverse()',ctx);assert.equal(ctx.system.market.live_valid,false);assert.equal(ctx.system.market.mode,'盤中資料不足');assert.equal(rendered,true);
});
check('Complete fresh scan preserves screener filters',()=>{
 let filtered=false;const instant=Date.parse('2026-10-13T01:01:00Z');const ctx={market:Object.fromEntries(Array.from({length:700},(_,i)=>[String(1000+i),{live:true,date:'2026-10-13',time:'09:00:00',price:103,prev:100,high:103,low:100,vol:100}])),system:{universe:Array(1951),market:{}},Date:class extends Date{constructor(){super(instant)}static now(){return instant}},taipeiDay:()=> '2026-10-13',clamp:(v,a,b)=>Math.max(a,Math.min(b,v)),liveItem:(code,m)=>({code,score:80,change_pct:3}),renderSystem:()=>{filtered=true}};
 vm.runInNewContext(source('haltLiveRanks')+'\n'+source('scanLiveUniverse')+';scanLiveUniverse()',ctx);assert.equal(ctx.system.market.live_valid,true);assert.equal(ctx.system.market.live_count,700);assert.equal(ctx.system.attack.length,12);assert.equal(filtered,true);assert.doesNotMatch(source('scanLiveUniverse'),/renderRank\(/);
});
check('Native UI cache is read on startup and APK version advances',()=>{assert.ok(activity.includes('new java.io.FileInputStream(cached)'));assert.ok(fs.readFileSync('app/build.gradle','utf8').includes('versionCode 30'))});
check('Native feed callback renders saved holdings and close PnL',()=>{
 const elements={holdingsGrid:{},totalPnl:{},portfolioRisk:{},sysStatus:{}};
 const ctx={JEI_PRIVATE_APP:true,holdings:[{code:'2609',name:'測試持股',cost:60,shares:1000}],market:{},system:{},$:id=>elements[id],tradingWindow:()=>false,renderSystem:()=>{},showFeedStatus:()=>{},money:n=>String(Math.round(n)),clamp:(v,a,b)=>Math.max(a,Math.min(b,v)),holdingAdvice:()=>({score:80,sector:'航運',sectorScore:80}),holdingDiagnosis:()=>({tag:'測試',conf:50,why:'',instText:''})};
 const start=html.indexOf('window.JEI_NATIVE={'),end=html.indexOf('\nfunction init()',start);ctx.window={};
 vm.runInNewContext(source('escapeMarketText')+'\n'+source('seedMarketFromSystem')+'\n'+source('renderHoldings')+'\n'+html.slice(start,end),ctx);
 ctx.window.JEI_NATIVE.onSystemData(JSON.stringify({quotes:{'2609':{price:66,change_pct:10,data_date:'2026-10-12'}},holdings:{},market:{}}));
 assert.equal(elements.totalPnl.textContent,'+NT$ 6000');assert.ok(elements.holdingsGrid.innerHTML.includes('2026-10-12'));assert.ok(elements.holdingsGrid.innerHTML.includes('+10.0%'));
 ctx.window.JEI_NATIVE.onSystemData('invalid JSON');assert.equal(elements.sysStatus.textContent,'JEI feed 格式錯誤');
});
check('Committed official close quotes cover stock and ETF without private fields',()=>{
 const feed=JSON.parse(fs.readFileSync('remote/system.json','utf8'));assert.equal(Object.keys(feed.holdings).length,0);assert.ok(Object.keys(feed.quotes).length>=1959);assert.ok(feed.quotes['2609'].price>0);assert.ok(feed.quotes['00937B'].price>0);for(const q of Object.values(feed.quotes))for(const k of ['cost','shares','pnl','market_value'])assert.equal(q[k],undefined);
});

console.log(`JEI smoke summary: ${passed}/${passed+failed} passed (${Math.round(100*passed/(passed+failed))}%)`);
if(passed+failed<18){console.error('FAIL expected at least 18 independent checks');process.exitCode=1;}
