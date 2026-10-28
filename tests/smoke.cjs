const fs=require('node:fs');const assert=require('node:assert/strict');const html=fs.readFileSync('remote/index.html','utf8');const paper=fs.readFileSync('remote/paper.html','utf8');const py=fs.readFileSync('scripts/update_system.py','utf8');const manifest=fs.readFileSync('app/src/main/AndroidManifest.xml','utf8');const activity=fs.readFileSync('app/src/main/java/com/jei/stockradar/MainActivity.java','utf8');
let passed=0,failed=0;
function check(label,fn){try{fn();passed++;console.log('PASS',label)}catch(e){failed++;console.error('FAIL',label,e.stack||e.message);process.exitCode=1}}
check('Public page guards private routes',()=>{assert.match(html,/function go\(id\)\{if\(!JEI_PRIVATE_APP/);assert.match(html,/function loadHoldings\(\)\{if\(!JEI_PRIVATE_APP/)});
check('No public portfolio nodes removed (prevents JS null dereference)',()=>assert.doesNotMatch(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>el\.remove\(\)\)/));
check('Public feed allows only safe ticker signals, never private positions',()=>{assert.match(py,/is_safe_public_holdings\(out\.get\("holdings"\)\)/);assert.match(html,/system\.holdings=JEI_PRIVATE_APP\?/)});
check('Android public static feed failover is restricted',()=>{const worker=fs.readFileSync('app/src/main/java/com/jei/stockradar/RiskWorker.java','utf8');assert.ok(activity.includes('getRemoteStatic(pageUrl)')&&activity.includes('getRemoteStatic(SYSTEM_JSON)')&&activity.includes('getRemoteStatic(UPDATE_JSON)')&&activity.includes('getRemoteStatic(sourceUrl)'));assert.ok(worker.includes('getStaticFeed(SYSTEM_JSON)')&&worker.includes('getStaticFeed(UPDATE_JSON)'));assert.ok(activity.includes('raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/'));assert.ok(worker.includes('raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/'))});
check('Published Android manifest matches app version',()=>{
 const gradle=fs.readFileSync('app/build.gradle','utf8');
 const update=JSON.parse(fs.readFileSync('remote/update.json','utf8'));
 const vc=gradle.match(/versionCode\s+(\d+)/);
 const vn=gradle.match(/versionName\s+'([^']+)'/);
 assert.ok(vc&&vn);
 assert.ok(update.versionCode<=Number(vc[1]),'manifest must not advertise an unbuilt Android version');
 if(update.versionCode===Number(vc[1]))assert.ok(update.versionName.startsWith(vn[1]));
 assert.match(update.url,/^https:\/\/github\.com\/alwaysjei1234-sys\/JEI-Stock-Radar\/releases\/download\/jei-latest\//);
});
check('Packaged Android offline fallback includes current risk and privacy gates',()=>{
 const fallback=fs.readFileSync('app/src/main/assets/index.html','utf8');
 const version=fallback.match(/const UI_VERSION='([^']+)'/)?.[1];
 assert.ok(version&&version!=='3.9.0-free-ai','stale APK emergency UI was not replaced');
 for(const required of [
  'function isTrustedFeed(','function holdingQuoteQuality(','function renderHoldAlerts(',
  'function renderNativeAlertHistory(','function holdingMarketPressure(',
  'function taipeiDateParts(','function tradingWindowAt(',
  'JEI_PRIVATE_APP','window.JEI_NATIVE=','window.JEI_STATIC='
 ])assert.ok(fallback.includes(required),'missing offline safeguard: '+required);
 assert.match(fallback,/function loadHoldings\(\)\{if\(!JEI_PRIVATE_APP/);
 assert.match(fallback,/\|\|!q\.valid\|\|String\(m\.quoteDay\)!==today/);
 assert.ok(fallback.includes('暫不提供賣出排序'),'offline local AI cannot bypass stale quote gate');
 const scripts=[...fallback.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
 assert.ok(scripts.length,'emergency UI needs inline JS');
 for(const [,code] of scripts) new (require('node:vm').Script)(code);
});
check('Offline Android UI includes latest manual notification diagnostic without sharing portfolio',()=>{
 const offline=fs.readFileSync('app/src/main/assets/index.html','utf8');
 assert.ok(offline.includes('function testNativeRiskNotification()'));
 const update=JSON.parse(fs.readFileSync('remote/update.json','utf8'));
 assert.ok(offline.includes("const UI_VERSION='"+update.uiVersion+"';"));
 assert.ok(offline.includes('JEI_PRIVATE_APP'));
 assert.ok(html.includes("const UI_VERSION='"+update.uiVersion+"';"));
});
check('Android backups disabled',()=>assert.match(manifest,/android:allowBackup="false"/));
check('WebView file-origin crossing disabled',()=>{assert.match(activity,/setAllowFileAccessFromFileURLs\(false\)/);assert.match(activity,/setAllowUniversalAccessFromFileURLs\(false\)/)});
check('Private native quotes prioritise holdings and accept alphanumeric bond ETFs',()=>{
 const {Script}=require('node:vm');
 const src=html.match(/let liveScanCycle=0;\nfunction liveCodes\(\)\{[\s\S]*?(?=\nfunction taipeiDateParts)/)?.[0];
 assert.ok(src,'mobile scan list must be extractable');
 const candidates=Array.from({length:1980},(_,i)=>({code:String(1000+i)}));
 const c={holdings:[{code:'00988B'},{code:'7711'}],system:{
  universe:candidates,attack:[{code:'2344'},{code:'00988B'}],next:[],monster:[],
  tomorrow_monster:[],future_monster:[],rotate:[],sectors:[{leaders:[{code:'3333'}]}]
 }};
 require('node:vm').runInNewContext(src+';globalThis.pick=liveCodes;',c);
 const first=c.pick(),second=c.pick();
 assert.equal(first[0],'00988B','ETF must be first in personal holdings scan');
 assert.equal(first[1],'7711','ordinary shares next');
 assert.ok(first.includes('2344')&&first.includes('3333'),'cloud attack and sector leaders are prioritised');
 assert.ok(first.length<=240,'phone cannot request the full 1900-stock universe');
 assert.ok(first.length>20,'limited rotating discovery still occurs');
 assert.ok(second.some(x=>!first.includes(x)),'repeated scans rotate through further symbols');

 const start=html.indexOf('function ingestMarket(j){'),end=html.indexOf('\nfunction liveItem(',start);
 assert.ok(start>0&&end>start);
 const ctx={market:{},liveScanReceived:0,lastMarketAt:'',taipeiDateParts:()=>({
  year:'2026',month:'10',day:'19'
 }),applyLiveRanks:()=>{ctx.ranksUpdated=true},renderHoldings:()=>{},renderUpdateStamp:()=>{},
 holdingQuoteQuality:()=>({valid:true}),$:(id)=>({
  classList:{toggle:()=>{}},set textContent(v){ctx.status=v}
 })};
 require('node:vm').runInNewContext(html.slice(start,end)+';globalThis.ingest=ingestMarket;',ctx);
 ctx.ingest({msgArray:[
  {c:'00988B',n:'測試 ETF',d:'20261019',z:'15.68',y:'15.1',t:'10:12:00'},
  {c:'2330',n:'數字股票',d:'20261019',z:'120',y:'118',t:'10:12:00'},
  {c:'00999B',d:'20261018',z:'20',y:'19',t:'10:12:00'}
 ]});
 assert.equal(ctx.market['00988B'].price,15.68);
 assert.equal(ctx.market['00988B'].quoteKind,'last_trade');
 assert.equal(ctx.market['2330'].price,120);
 assert.equal(ctx.market['00999B'],undefined,'previous session ETF quote must be rejected');
 assert.equal(ctx.ranksUpdated,true,'cloud shortlist is overlaid with fresh quotes');
 assert.ok(!html.includes('scanLiveUniverse();renderHoldings();renderUpdateStamp()'),
   'partial mobile sample cannot replace the broad-market cloud leaderboards');
 const worker=fs.readFileSync('app/src/main/java/com/jei/stockradar/RiskWorker.java','utf8');
 assert.ok(worker.includes('code.matches("[0-9]{4,6}[A-Za-z]?")'));
 assert.ok(worker.includes('code.equalsIgnoreCase(h.optString("code", ""))'));
 assert.ok(html.includes("window.location.reload()"),'web refresh UI must not be an inert button');
});

check('Stock screener and heatmap wired',()=>{assert.match(html,/function renderAttackScreener\(/);assert.match(html,/function renderSectorHeatmap\(/);assert.match(html,/renderSectors\(\);renderSectorHeatmap\(\)/)});
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(Boolean);const vm=require('node:vm');check('Inline JavaScript syntax',()=>{for(const code of scripts)new vm.Script(code)});

check('Trading hours use Asia/Taipei timezone',()=>assert.match(html,/function taipeiDateParts\(.*timeZone:'Asia\/Taipei'/));
check('Screener updates freshness label',()=>assert.match(html,/function renderAttackScreener\(\)\{\s*updateFeedFreshness\(\)/));
check('Private sections are hidden without removal',()=>assert.match(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>\{el\.style\.display='none'/));

check('WebView external links open outside app',()=>assert.ok(activity.includes('shouldOverrideUrlLoading')&&activity.includes('Intent.ACTION_VIEW')));
check('Mixed content blocked',()=>assert.ok(activity.includes('MIXED_CONTENT_NEVER_ALLOW')));

check('Sector dropdown is wired into stock screening',()=>assert.ok(html.includes('id="screenSector"')&&html.includes('function syncScreenSectors()')&&html.includes("['screenScore','screenPriceMax','screenRiseMax','screenQuery','screenSector','screenOrder']")));

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
 const src=html.split('\n').filter(x=>/^(function taipeiDateParts\(|function tradingWindowAt\(|function tradingWindow\()/.test(x)).join('\n');
 const ctx={Intl};vm.runInNewContext(src+';globalThis.testTrading=tradingWindowAt;',ctx);
 assert.equal(ctx.testTrading(new Date('2026-10-13T01:00:00Z')),true,'Tuesday 09:00 Taipei must be trading');
 assert.equal(ctx.testTrading(new Date('2026-10-13T05:29:00Z')),true,'Tuesday 13:29 Taipei still trades');
 assert.equal(ctx.testTrading(new Date('2026-10-13T05:30:00Z')),false,'Tuesday 13:30 Taipei market closed');
 assert.equal(ctx.testTrading(new Date('2026-10-13T07:00:00Z')),false,'Tuesday 15:00 Taipei must be closed');
 assert.equal(ctx.testTrading(new Date('2026-10-17T01:00:00Z')),false,'Saturday 09:00 Taipei must be closed');
});

check('Stock screener filters score, price, sector, and stale market at runtime',()=>{
 const start=html.indexOf('function renderAttackScreener(){'),end=html.indexOf('const SCREEN_PREFS_KEY=',start);
 assert.ok(start>=0&&end>start);const fn=html.slice(start,end);
 const els={screenScore:{value:'75'},screenPriceMax:{value:'120'},screenRiseMax:{value:'9'},screenQuery:{value:''},screenSector:{value:'AI'},screenOrder:{value:'score'},screenCount:{textContent:''}};
 let captured=[],trusted=true;const ctx={isTrustedFeed:()=>trusted,isRecentCloseObservation:()=>false,system:{attack:[{code:'1111',score:90,sector:'AI',price:100,change_pct:3},{code:'2222',score:60,sector:'AI',price:90,change_pct:2},{code:'3333',score:95,sector:'航運',price:70,change_pct:2},{code:'4444',score:99,sector:'AI',price:500,change_pct:4}],market:{mode:'今日收盤'},data_date:'2026-10-13'},$:id=>els[id],renderRank:(_id,arr)=>{captured=arr},updateFeedFreshness:()=>{},syncScreenSectors:()=>{}};
 vm.runInNewContext(fn+';globalThis.testScreen=renderAttackScreener;',ctx);ctx.testScreen();assert.equal(captured.length,1);assert.equal(captured[0].code,'1111');
 ctx.system.market.mode='盤中資料不足';trusted=false;ctx.testScreen();assert.equal(captured.length,0);
});

check('Feed freshness rejects old, stale, or mislabeled intraday quotes',()=>{
 const line=html.match(/^function isTrustedFeed\(.*$/m)?.[0];assert.ok(line);
 const ctx={};vm.runInNewContext(line+';globalThis.verify=isTrustedFeed;',ctx);
 const day=new Date('2026-10-14T02:00:00Z');
 const ok={updated_at:'2026-10-14 10:00',data_date:'2026-10-14',market:{mode:'盤中即時',stale:false,live_valid:true,live_count:1900,close_count:1900}};
 assert.equal(ctx.verify(ok,day),true);
 assert.equal(ctx.verify({...ok,data_date:'2026-10-13'},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,stale:true}},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,mode:'資料過期'}},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,live_valid:false}},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,mode:'今日收盤',live_valid:false}},day),false,'official close cannot be reported at 10:00');
 assert.equal(ctx.verify({...ok,market:{...ok.market,mode:'今日收盤',close_count:0}},day),false);
 const after=new Date('2026-10-14T06:00:00Z');
 const close={...ok,updated_at:'2026-10-14 13:45',market:{mode:'今日收盤',stale:false,live_valid:false,close_count:1900}};
 assert.equal(ctx.verify(close,after),true,'confirmed official close at 14:00');
 assert.equal(ctx.verify({...close,market:{...close.market,close_count:499}},after),false,'official close requires 500+ covered stocks');
 assert.equal(ctx.verify({...close,updated_at:'2026-10-14 10:00'},after),false,'pre-close snapshot cannot claim to be official close');
 assert.equal(ctx.verify({...ok,market:{...ok.market,live_count:499}},day),false,'thin live coverage is untrusted');
 assert.equal(ctx.verify(ok,after),false,'old intraday feed cannot count as live after close');
 assert.equal(ctx.verify({...ok,updated_at:'2026-10-14 09:00'},day),false,'old but same-day intraday feed must fail');
 assert.equal(ctx.verify({...ok,updated_at:'2026-10-14 10:05'},day),false,'future feed timestamp must fail');
});
check('Off-hours official close observation is readable but never trusted as live',()=>{
 const source=html.match(/function isRecentCloseObservation\(feed=system,now=new Date\(\)\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(source,'explicit dated historical-read-only boundary');
 const ctx={};vm.runInNewContext(source+';globalThis.recent=isRecentCloseObservation;',ctx);
 const now=new Date('2026-10-15T01:30:00Z');
 const close={data_date:'2026-10-14',updated_at:'2026-10-14 21:09',market:{mode:'今日收盤',stale:false,close_count:1959}};
 assert.equal(ctx.recent(close,now),true,'last official close usable before open');
 assert.equal(ctx.recent({...close,market:{...close.market,stale:true}},now),false);
 assert.equal(ctx.recent({...close,updated_at:'2026-10-14 10:00'},now),false,'pre-close stamp invalid');
 assert.equal(ctx.recent({...close,market:{...close.market,close_count:499}},now),false,'thin archive invalid');
 assert.equal(ctx.recent({...close,data_date:'2026-10-02',updated_at:'2026-10-02 21:09'},now),false,'old snapshot invalid');
 assert.ok(html.includes('!archive&&x.entry_low!=null'),'historical watchlists hide entry/target price plans');
 assert.ok(html.includes('歷史收盤觀察榜'));
 assert.ok(html.includes('const historical=!trusted&&isRecentCloseObservation(system,now)'));
});
check('Weekday typhoon and exchange-holiday closes stay historical, never actionable',()=>{
 const trusted=html.match(/^function isTrustedFeed\(.*$/m)?.[0];
 const recent=html.match(/function isRecentCloseObservation\(feed=system,now=new Date\(\)\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(trusted&&recent,'feed date gates must exist');
 const ctx={};vm.runInNewContext(trusted+'\n'+recent+';globalThis.trusted=isTrustedFeed;globalThis.recent=isRecentCloseObservation;',ctx);
 const prior={data_date:'2026-10-22',updated_at:'2026-10-22 20:22',market:{mode:'今日收盤',stale:false,close_count:1955}};
 const typhoonClosure=new Date('2026-10-23T05:00:00Z');
 const makeUpHoliday=new Date('2026-10-26T01:00:00Z');
 assert.equal(ctx.trusted(prior,typhoonClosure),false,'Friday suspension cannot be treated as a current close');
 assert.equal(ctx.recent(prior,typhoonClosure),true,'last verified close remains available as historical context');
 assert.equal(ctx.trusted(prior,makeUpHoliday),false,'Monday holiday cannot be treated as a current close');
 assert.equal(ctx.recent(prior,makeUpHoliday),true,'multi-day holiday retains a dated prior close');
});
check('Private AI token setup is reachable and does not consume model quota',()=>{
 assert.ok(html.includes('id="aiBackendToken" type="password"'),'private token field must be visible');
 assert.ok(html.includes('id="aiTokenStatus"'));
 assert.ok(html.includes('onclick="verifyAiToken()"'));
 assert.ok(html.includes("action:'verify_token'"));
 const api=fs.readFileSync('api/consult.js','utf8');
 assert.ok(api.includes('if(body.action==="verify_token")'),'auth-only ping must exist on server');
 assert.ok(api.indexOf('if(got!==expected)')<api.indexOf('if(body.action==="verify_token")'),'authorization before ping');
 assert.ok(html.includes('更新 → 免費多 AI 設定'),'missing-token guidance must name visible screen');
});

check('Exchange quote dates and 13:30 close boundary are enforced',()=>{
 assert.ok(py.includes('if quote_day!=expected_day:')&&py.includes('if not valid_trade_time:'));
 assert.ok(py.includes('(hh<13 or mm<=30)'));
 assert.ok(py.includes('live_valid=market_open and live_count>=500'));
 assert.ok(py.includes('market_mode="資料過期" if stale_source'));
 assert.ok(html.includes('liveBad=!isTrustedFeed()'));
 assert.ok(html.includes("arr=[];empty='有效行情尚未驗證"),'untrusted radar lists must halt without recent official close');
});

check('Paper trading has no broker order submission',()=>{
 assert.ok(activity.includes('PAPER_UI'));assert.ok(paper.includes('jei-paper-trades-v1'));
 assert.doesNotMatch(paper,/XMLHttpRequest|WebSocket|\/api\/orders|placeOrder\(/);
 assert.ok(paper.includes('JEINative.fetchStaticJson(kind)'),'native bridge may only read verified feed');
});

check('Paper ledger JavaScript syntax',()=>{for(const match of paper.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(match[1])});
check('Paper PnL charges both-side fees and sell-side tax',()=>{
 const line=paper.split('\n').find(x=>x.startsWith('function calc('));assert.ok(line);
 const ctx={};vm.runInNewContext(line+';globalThis.testCalc=calc;',ctx);
 const t={side:'long',entry:100,exit:110,qty:1000,fee:0.001425,tax:0.0015};
 const p=ctx.testCalc(t);assert.equal(p.gross,10000);assert.ok(Math.abs(p.fees-299.25)<1e-8);assert.equal(p.tax,165);assert.ok(Math.abs(p.net-9535.75)<1e-8);
 const short=ctx.testCalc({...t,side:'short'});assert.equal(short.gross,-10000);assert.equal(short.tax,150);
});

check('Paper scanner is read-only and halts on insufficient market coverage',()=>{assert.ok(paper.includes("readJeiStatic('system')"));assert.ok(paper.includes("const valid=validFeedDate(feed)"));assert.ok(paper.includes("if(!valid)return"));assert.doesNotMatch(paper,/\/api\/orders|placeOrder\(/);assert.ok(paper.includes('JEINative.fetchStaticJson(kind)'))});

check('Day-trade legacy scanner accepts valid dated prices and refuses stale signals',()=>{
 const mode=paper.match(/function signalFeedMode\(feed,now=new Date\(\)\)\{[\s\S]*?(?=\nfunction validFeedDate)/)?.[0];
 const validator=paper.match(/^function validFeedDate\(feed,now=new Date\(\)\).*$/m)?.[0];
 assert.ok(mode&&validator,'verified feed validator must exist');
 const ctx={twDay:()=> '2026-10-14'};
 vm.runInNewContext(mode+'\n'+validator+';globalThis.verify=validFeedDate;',ctx);
 const at=new Date('2026-10-14T02:00:00Z');
 const live={data_date:'2026-10-14',updated_at:'2026-10-14 10:00',market:{mode:'盤中即時',stale:false,live_valid:true,live_count:1959}};
 const close={data_date:'2026-10-14',updated_at:'2026-10-14 13:45',market:{mode:'今日收盤',stale:false,live_valid:false,close_count:1959}};
 assert.equal(ctx.verify(live,at),true,'current validated live feed');
 assert.equal(ctx.verify(close,at),false,'official close is invalid before 13:30');
 const afterClose=new Date('2026-10-14T06:00:00Z');
 assert.equal(ctx.verify(close,afterClose),true,'today official close after 13:30');
 assert.equal(ctx.verify({...close,updated_at:'2026-10-14 10:00'},afterClose),false,'pre-close feed mislabeled official close');
 assert.equal(ctx.verify({...live,market:{...live.market,live_count:499}},at),false,'weak live coverage rejected');
 assert.equal(ctx.verify({...close,market:{...close.market,close_count:3}},afterClose),false,'insufficient close coverage');
 assert.equal(ctx.verify({...live,updated_at:'2026-10-14 09:00'},at),false,'old intraday snapshot');
 assert.equal(ctx.verify({...live,updated_at:'2026-10-14 10:05'},at),false,'future timestamp');
 assert.equal(ctx.verify({...live,market:{...live.market,stale:true}},at),false,'stale flag');
 assert.equal(ctx.verify({...live,market:{...live.market,live_valid:false}},at),false,'unverified live');
 assert.equal(ctx.verify({...live,data_date:'2026-10-13'},at),false,'prior day');
 const codePattern='/^'+'\\d{4,6}$/';
 assert.ok(paper.includes(codePattern+'.test(p.code)'),'open positions must validate a normal stock code');
 assert.ok(paper.includes(codePattern+'.test(code)'),'scanner must validate a normal stock code');
 assert.ok(paper.includes("const valid=validFeedDate(feed)"));
 assert.ok(paper.includes("if(!valid)return"),'candidate list must gate on trusted feed');
});

check('Paper open positions are isolated from realized trades',()=>{assert.ok(paper.includes("jei-paper-open-positions-v1"));assert.ok(paper.includes("function loadPositions()"));assert.ok(paper.includes("function renderPositions()"));assert.ok(paper.includes("const list=load(),p=list.map(calc)"))});


const cash=fs.readFileSync('remote/cash.html','utf8');
check('Cash simulation JavaScript parses',()=>{const script=cash.match(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/);assert.ok(script);new vm.Script(script[1])});
check('Cash and day-trading local records remain separate',()=>{assert.ok(cash.includes('jei-cash-trades-v1'));assert.ok(cash.includes('jei-cash-open-positions-v1'));assert.ok(cash.includes('jei-cash-auto-watch-v1'));assert.ok(!paper.includes('jei-cash-trades-v1'))});
check('Cash simulation uses standard 0.3 percent stock sell tax',()=>{assert.ok(cash.includes('現股交易稅率（賣出）'));assert.ok(cash.includes('value="0.003"'))});
check('Cash simulation enforces capital and per-position limit',()=>{assert.ok(cash.includes('function cashMetrics()'));assert.ok(cash.includes('cost>m.cfg.limit||cost>m.available'));assert.ok(cash.includes('jei-cash-account-config-v1'))});

check('Cash paper close records only confirmed realized trades',()=>{assert.ok(cash.includes("id=\"closeTrade\""));assert.ok(cash.includes("function renderClose()"));assert.ok(cash.includes("reason:"));assert.ok(cash.includes("savePositions(positions)"));assert.ok(cash.includes("oldHistory=localStorage.getItem(KEY)"))});
check('Cash paper performance uses realized net of fees and tax',()=>{assert.ok(cash.includes("100*m.closed/m.cfg.capital"));assert.ok(cash.includes("closed.filter(t=>calc(t).net>0)"));assert.ok(cash.includes("tax:0.003"))});


check('Cash momentum strategy archive sync is independent of current radar',()=>{assert.ok(cash.includes("readJeiStatic('daily')"));assert.ok(cash.includes("async function syncDailyPrices()"));assert.ok(cash.includes("if(day<=t.day||day<=t.lastDay)continue"));assert.ok(cash.includes("if(t.strategies)strategyAdvance(t,price,day)"))});
check('Four cash exit strategies are present',()=>{assert.ok(cash.includes("id:'fixed5'"));assert.ok(cash.includes("id:'fixed7'"));assert.ok(cash.includes("id:'fixed10'"));assert.ok(cash.includes("id:'trailing'"))});

check('Cash auto scanner never closes strategies using intraday quotes',()=>{
 const scan=cash.split('\n').find(l=>l.startsWith('async function autoScan('));
 const archive=cash.split('\n').find(l=>l.startsWith('async function syncDailyPrices('));
 assert.ok(scan&&archive,'cash scanner and official archive updater must exist');
 assert.doesNotMatch(scan,/strategyAdvance\s*\(/);
 assert.match(archive,/if\(t\.strategies\)strategyAdvance\(t,price,day\)/);
});
check('Cash strategy net figures include both fees and sell tax',()=>{
 const defs=cash.split('\n').filter(l=>/^(const STRATEGIES=|function strategyAdvance\(|function strategyInit\(|function strategyNetPct\()/.test(l));
 assert.equal(defs.length,4);
 const ctx={};vm.runInNewContext(defs.join('\n')+';globalThis.step=strategyAdvance;globalThis.init=strategyInit;globalThis.net=strategyNetPct;',ctx);
 const t=ctx.init({day:'2026-10-13',startPrice:100,lastDay:'2026-10-13',lastPrice:100});
 ctx.step(t,110,'2026-10-13');assert.equal(t.strategies.fixed5.status,'觀察中','same-day close cannot trigger');
 ctx.step(t,106,'2026-10-14');assert.equal(t.strategies.fixed5.status,'收盤停利');assert.equal(t.strategies.fixed7.status,'觀察中');
 ctx.step(t,103,'2026-10-15');assert.equal(t.strategies.trailing.status,'移動停利觸發');assert.equal(t.strategies.fixed5.exitPrice,106);
 const net=ctx.net(100,106);
 assert.ok(net>5&&net<6,'net is below gross 6% after fees and tax');
 assert.equal(ctx.net(0,106),null);
});
check('Cash risk stale feed cannot qualify as fresh intraday',()=>{
 const line=cash.match(/function signalFeedMode\(feed,now=new Date\(\)\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(line);
 const ctx={twDay:()=> '2026-10-13'};
 vm.runInNewContext(line+';globalThis.mode=signalFeedMode;',ctx);
 const now=new Date('2026-10-13T02:15:00Z');
 const make=mode=>({data_date:'2026-10-13',updated_at:'2026-10-13 10:00',market:{stale:false,mode,live_valid:true,live_count:1800,close_count:1800}});
 assert.equal(ctx.mode(make('資料過期'),now),'');
 const afterClose=new Date('2026-10-13T06:00:00Z');
 const validClose={...make('今日收盤'),updated_at:'2026-10-13 13:45'};
 assert.equal(ctx.mode(validClose,now),'','before 13:30 no official close');
 assert.equal(ctx.mode(validClose,afterClose),'今日正式收盤觀察');
 assert.equal(ctx.mode({...validClose,updated_at:'2026-10-13 10:00'},afterClose),'','pre-close stamp rejected');
 assert.equal(ctx.mode({...validClose,market:{...validClose.market,close_count:1}},afterClose),'','incomplete close blocked');
 assert.equal(ctx.mode({...make('盤中即時'),market:{...make('盤中即時').market,live_count:499}},now),'','thin intraday feed rejected');
 assert.equal(ctx.mode(make('盤中即時'),now),'已驗證盤中觀察');
 assert.equal(ctx.mode({...make('盤中即時'),updated_at:'2026-10-13 09:00'},now),'','stale today intraday signal rejected');
 assert.equal(ctx.mode({...make('盤中即時'),data_date:'2026-10-12'},now),'');
});
check('Holdings only use confirmed executed exchange trades',()=>{
 assert.ok(html.includes("quoteKind:'last_trade'"));
 assert.ok(html.includes("price=Number(x?.z)"));
 const code=html.match(/function ingestMarket\(j\)\{[\s\S]*?(?=\nfunction liveItem)/)?.[0]||'';
 assert.ok(code.includes("date!==expected")&&code.includes("price<=0"));
 assert.doesNotMatch(code,/\(bid\+ask\)\/2|x\.b\)|x\.a\)/);
 const basic=html.split('\n').filter(x=>/^(function taipeiDateParts\(|function tradingWindowAt\(|function tradingWindow\()/.test(x)).join('\n');
 const quality=html.match(/function holdingQuoteQuality\(m,now=new Date\(\)\)\{[\s\S]*?(?=\nfunction seedMarketFromSystem)/)?.[0];
 assert.ok(quality,'quote quality function is loadable');
 const funcs=basic+'\n'+quality;
 const ctx={Intl};vm.runInNewContext(funcs+';globalThis.inspect=holdingQuoteQuality;',ctx);
 const during=new Date('2026-10-14T02:10:00Z'),post=new Date('2026-10-14T05:35:00Z');
 const mk=(minute=605,received='2026-10-14T02:07:00Z')=>({price:920,quoteDay:'20261014',quoteKind:'last_trade',quoteMinute:minute,receivedAt:Date.parse(received)});
 assert.equal(ctx.inspect(mk(605),during).valid,true,'recent executed trade qualifies');
 assert.equal(ctx.inspect(mk(590),during).valid,false,'old exchange trade time rejected even if freshly downloaded');
 assert.equal(ctx.inspect({...mk(605),quoteKind:'bid_ask'},during).valid,false);
 assert.equal(ctx.inspect({...mk(605),quoteDay:'20261013'},during).valid,false);
 assert.equal(ctx.inspect(mk(805,'2026-10-14T05:31:00Z'),post).valid,true,'end-session trade allowed as reference');
 assert.equal(ctx.inspect(mk(600,'2026-10-14T05:31:00Z'),post).valid,false,'midday price cannot become a closing reference');
});
check('Compact home and private holdings protect stale decisions',()=>{
 assert.ok(html.includes('id="homeQuick"')&&html.includes('id="quickRisk"')&&html.includes('id="quickHold"')&&html.includes('id="quickAttack"'));
 assert.ok(html.includes('function renderHomeQuick()')&&html.includes('function holdingQuoteQuality('));
 assert.ok(html.includes("if(!isTrustedFeed())return{score:'--'"));
 assert.ok(html.includes('safe(h.name)')&&html.includes('safe(d.instText)'),'portfolio-derived HTML must be escaped');
});
check('Private portfolios use date-stamped official closes after market hours',()=>{
 const source=html.match(/function applyOfficialCloseArchive\(data\)\{[\s\S]*?(?=\nfunction refreshOfficialCloses)/)?.[0];
 assert.ok(source,'official close bridge is present');
 assert.ok(html.includes("JEINative.fetchStaticJson('daily')"),'Android bridge reads public daily close without sending holdings');
 assert.ok(html.includes('window.JEI_STATIC={'));
 const ctx={JEI_PRIVATE_APP:true,holdings:[{code:'2330',name:'測試'}],market:{},renderHoldings:()=>{},
  holdingQuoteQuality:()=>({valid:false}),taipeiDateParts:()=>({year:'2026',month:'10',day:'14'}),
  Date:class extends Date{constructor(...args){super(...(args.length?args:['2026-10-14T02:20:00Z']))}}};
 vm.runInNewContext(source+';globalThis.apply=applyOfficialCloseArchive;',ctx);
 const data={schema:1,kind:'official_daily_close',days:{'2026-10-13':{'2330':900}}};
 assert.equal(ctx.apply(data),true);
 assert.equal(ctx.market['2330'].price,900);
 assert.equal(ctx.market['2330'].quoteDay,'20261013');
 assert.equal(ctx.market['2330'].quoteKind,'official_close');
 assert.equal(ctx.apply({...data,kind:'intraday_prices'}),false);
});
check('Cloud return and drawdown reporting is explicit',()=>{
 assert.ok(cash.includes('<th>估算總報酬</th><th>最大回撤</th>'));
 assert.ok(cash.includes('s.max_drawdown_pct'));
 assert.ok(cash.includes('Number(s.estimated_liquidation_equity_ntd)/basis-1'));
});


check('Private portfolio triage requires fresh dated exchange prices',()=>{
 assert.ok(html.includes('id="holdTriage"')&&html.includes('id="privateRotate"'));
 const fn=html.match(/function holdingTriageCategory\(h,m,quote,advice,ret,ch,trusted=isTrustedFeed\(\),now=new Date\(\)\)\{[\s\S]*?(?=\nfunction buildPrivatePortfolioTriage)/)?.[0];
 assert.ok(fn,'triage classifier present');
 const ctx={taipeiDateParts:()=>({year:'2026',month:'10',day:'14'}),isTrustedFeed:()=>true};
 vm.runInNewContext(fn+';globalThis.classify=holdingTriageCategory;',ctx);
 const h={code:'1234'},m={price:88,quoteDay:'20261014'},q={valid:true};
 const call=(advice,ret=0,ch=0,feed=true,quote=q,data=m)=>ctx.classify(h,data,quote,advice,ret,ch,feed,new Date('2026-10-14T02:15:00Z'));
 assert.equal(call({score:31,sectorScore:36,action:'續抱觀察'},-20,-2).id,'defense');
 assert.equal(call({score:55,sectorScore:54,action:'移動停利'},20,-2).id,'profit');
 assert.equal(call({score:40,sectorScore:40,action:'一般'},-2,-1).id,'rotation');
 assert.equal(call({score:80,sectorScore:75,action:'續抱偏多'},10,1).id,'hold');
 assert.equal(call({score:55,sectorScore:50,action:'中性'},1,0).id,'watch');
 assert.equal(call({score:30,sectorScore:40,action:'風控優先'},-20,-5,false).id,'pending');
 assert.equal(call({score:30,sectorScore:40,action:'風控優先'},-20,-5,true,q,{price:88,quoteDay:'20261013'}).id,'pending');
 assert.equal(call({score:'--',sectorScore:40,action:'風控優先'},-20,-5).id,'pending');
});
check('Rotation candidates exclude held names and stale feed',()=>{
 assert.ok(html.includes('!holdings.some(h=>h.code===String(x.code))'));
 assert.ok(html.includes("Number(x.score)>=70"));
 assert.ok(html.includes('Number(system.risk?.score)>=70'));
 assert.ok(html.includes("if(!JEI_PRIVATE_APP)return;"));
});
check('Four-strategy leaderboard needs matched sufficient closes',()=>{
 const cash=fs.readFileSync('remote/cash.html','utf8');
 const fn=cash.match(/function strategyComparison\(data\)\{[\s\S]*?(?=\nfunction renderStrategyComparison)/)?.[0];
 assert.ok(fn,'comparison helper present');
 const ctx={};vm.runInNewContext(fn+';globalThis.compare=strategyComparison;',ctx);
 const keys=['fixed5','fixed7','fixed10','trailing'];
 const make=(closed=2,days=4,coverage='2/2')=>({capital_per_strategy:1000000,strategies:Object.fromEntries(keys.map((k,i)=>[k,{summary:{closed,open_positions:2,estimated_liquidation_equity_ntd:1000000+(i+1)*1000,max_drawdown_pct:i+1,official_close_coverage:coverage},equity_history:Array.from({length:days},(_,j)=>({day:'2026-10-'+String(1+j).padStart(2,'0'),equity:1000000}))}]))});
 assert.equal(ctx.compare(make()).ready,false,'2 trades cannot be ranked');
 assert.equal(ctx.compare(make(12,11,'1/2')).ready,false,'missing official closes invalidate ranking');
 const good=ctx.compare(make(12,11,'2/2'));
 assert.equal(good.ready,true);
 assert.equal(good.ranked[0].id,'trailing','ranks by net portfolio return when comparable');
 assert.equal(ctx.compare(make(12,2,'2/2')).ready,false,'too-short observation period cannot qualify');
 assert.equal(ctx.compare({...make(12,11,'2/2'),capital_per_strategy:0}).ready,false);
});
check('Manual cash candidate browsing rejects stale feeds',()=>{
 const cash=fs.readFileSync('remote/cash.html','utf8');
 assert.ok(cash.includes('const valid=validFeedDate(feed)'));
 assert.ok(cash.includes('行情過期或未驗證，暫停候選訊號'));
});


check('Premium mobile watchlist has verified-feed strip and expandable private holdings',()=>{
 assert.ok(html.includes('id="feedGate"')&&html.includes('function updateFeedGate()'));
 assert.ok(html.includes('id="holdFilter"')&&html.includes('id="holdSort"')&&html.includes('id="holdShown"'));
 assert.ok(html.includes('class="watchDetails"')&&html.includes('function setHoldView('));
 assert.ok(html.includes('const openCodes=new Set('),'expanded details must survive refresh');
 assert.ok(html.includes('safe(h.name)')&&html.includes('safe(d.instText)'));
 const updater=html.match(/function updateFeedGate\(\)\{[\s\S]*?(?=\nfunction renderUpdateStamp)/)?.[0];
 assert.ok(updater,'freshness status renderer present');
 const el={className:'',textContent:''},ctx={$:id=>id==='feedGate'?el:null,system:{market:{mode:'盤中即時'}},isTrustedFeed:()=>false,isRecentCloseObservation:()=>false};
 vm.runInNewContext(updater+';globalThis.update=updateFeedGate;',ctx);
 ctx.update();assert.match(el.textContent,/行情資料未通過/);assert.match(el.className,/stale/);
 ctx.isTrustedFeed=()=>true;ctx.update();assert.match(el.textContent,/今日盤中已驗證/);
});
check('Holdings row filters and PnL sorts work independently of risk category',()=>{
 const src=html.match(/function sortedHoldingRows\(rows,filter=holdViewFilter,order=holdViewOrder\)\{[\s\S]*?(?=\nfunction renderHoldings)/)?.[0];
 assert.ok(src);
 const ctx={holdViewFilter:'all',holdViewOrder:'priority'};
 vm.runInNewContext(src+';globalThis.sortRows=sortedHoldingRows;',ctx);
 const rows=[
  {h:{code:'1001',cost:50,shares:100},price:40,category:{id:'defense',rank:0},advice:{score:25}},
  {h:{code:'1002',cost:60,shares:100},price:80,category:{id:'hold',rank:3},advice:{score:80}},
  {h:{code:'1003',cost:30,shares:100},price:NaN,category:{id:'pending',rank:5},advice:{score:'--'}}
 ];
 assert.equal(ctx.sortRows(rows,'all','priority')[0].h.code,'1001');
 assert.equal(ctx.sortRows(rows,'hold','priority').length,1);
 assert.equal(ctx.sortRows(rows,'all','pnlDesc')[0].h.code,'1002');
 assert.equal(ctx.sortRows(rows,'all','pnlAsc')[0].h.code,'1001');
 assert.equal(ctx.sortRows(rows,'all','pnlAsc')[2].h.code,'1003','unpriced holdings sort last');
 assert.equal(ctx.sortRows(rows,'all','name')[2].h.code,'1003');
});
check('Sector and backtest feeds are escaped before DOM insertion',()=>{
 const sector=html.match(/function renderSectors\(\)\{[\s\S]*?(?=\nfunction renderBacktest)/)?.[0];
 const backtest=html.match(/function renderBacktest\(\)\{[^\n]+/)?.[0];
 const escape=html.match(/^function escapeMarketText\(.*$/m)?.[0];
 assert.ok(sector&&backtest&&escape);
 const els={sectorList:{innerHTML:''},sectorTop:{innerHTML:''},backtestBox:{innerHTML:''}};
 const evil='<img src=x onerror=alert(1)>';
 const ctx={isTrustedFeed:()=>true,system:{sectors:[{name:evil,score:85,avg_pct:4,breadth:90,value_billion:10,leaders:[{code:'2330',name:evil,pct:5}]}],backtest:{hit3:evil,hit5:50,hit10:20,samples:2}},$:id=>els[id]};
 vm.runInNewContext(escape+'\n'+sector+'\n'+backtest+';globalThis.render=[renderSectors,renderBacktest];',ctx);
 ctx.render[0]();ctx.render[1]();
 assert.doesNotMatch(els.sectorList.innerHTML,/<img/i);
 assert.doesNotMatch(els.sectorTop.innerHTML,/<img/i);
 assert.doesNotMatch(els.backtestBox.innerHTML,/<img/i);
 assert.match(els.sectorList.innerHTML,/&lt;img/);
 assert.match(els.backtestBox.innerHTML,/&lt;img/);
});
check('Quick AI holding answers require trusted per-stock quotes',()=>{
 const source=html.match(/function chatHolding\(stock\)\{[\s\S]*?(?=\nfunction chatStockInfo)/)?.[0];
 assert.ok(source);
 const state={trusted:false,quoteDay:'20261013',valid:true};
 const ctx={JEI_PRIVATE_APP:true,holdings:[{code:'2330',name:'測試股',cost:100,shares:1000}],market:{2330:{price:90,quoteDay:state.quoteDay}},holdingQuoteQuality:()=>({valid:state.valid,label:'官方收盤・非即時'}),taipeiDateParts:()=>({year:'2026',month:'10',day:'14'}),isTrustedFeed:()=>state.trusted,holdingAdvice:()=>({action:'測試賣出',reason:'不應顯示',defense:80,target1:110,target2:120}),holdingDiagnosis:()=>({tag:'測試',why:'測試',instText:'測試'})};
 vm.runInNewContext(source+';globalThis.answer=chatHolding;',ctx);
 const stock={code:'2330',name:'測試股'};
 assert.match(ctx.answer(stock),/暫不提供賣出排序/);
 assert.doesNotMatch(ctx.answer(stock),/測試賣出|目標1/);
 state.trusted=true;
 assert.match(ctx.answer(stock),/暫不提供賣出排序/,'stale individual quote blocks advice even with fresh market feed');
 state.quoteDay='20261014';ctx.market['2330'].quoteDay=state.quoteDay;
 assert.match(ctx.answer(stock),/測試賣出/,'verified same-day quote permits labelled reference guidance');
 state.valid=false;
 assert.match(ctx.answer(stock),/暫不提供賣出排序/,'unverified price must be blocked');
});
check('Quick AI market gate runs before generic advice and requires verified triage',()=>{
 const source=html.match(/function answerChat\(q\)\{[\s\S]*?(?=\nfunction sendChat)/)?.[0];
 assert.ok(source);
 const ctx={findChatStock:()=>null,isTrustedFeed:()=>false,holdings:[{name:'測試股',code:'2330'}],system:{risk:{score:12,cash:'低'}},JEI_PRIVATE_APP:true};
 vm.runInNewContext(source+';globalThis.answer=answerChat;',ctx);
 assert.match(ctx.answer('測試股怎麼辦'),/暫停即時風險判斷/);
 assert.match(ctx.answer('我的持股哪檔該賣'),/暫停即時風險判斷/);
 assert.ok(source.includes("buildPrivatePortfolioTriage().filter(x=>x.category.id!=='pending')"),'pending holdings cannot be ranked');
});
check('Quick AI chat never labels stale quotes as live and never ranks stale alerts',()=>{
 const src=html.match(/function chatHolding\(stock\)\{[\s\S]*?(?=\nfunction chatStockInfo)/)?.[0];
 assert.ok(src);
 assert.ok(src.includes('holdingQuoteQuality(m)'),'private quotes must be verified before AI holding figures');
 assert.ok(src.includes('價格參考')&&!src.includes('現價'));
 assert.ok(html.includes('if(!isTrustedFeed())return String(stock.code)'));
 assert.ok(html.includes('行情或市場資訊未經今日有效驗證'));
});
check('Mobile paper scorecard surfaces qualification before leaderboard',()=>{
 const cash=fs.readFileSync('remote/cash.html','utf8');
 assert.ok(cash.includes('id="cloudKpiStatus"')&&cash.includes('id="cloudKpiLeader"')&&cash.includes('id="cloudKpiDate"'));
 assert.ok(cash.includes('result.ready?result.ranked[0].label'));
 assert.ok(cash.includes("$('cloudKpiStatus').textContent='資料失敗'"));
});


check('Private holding alert engine uses fresh executed intraday trades only',()=>{
 const source=html.match(/function holdingAlertSignal\(h,m,quality,prefs,observed,now=new Date\(\),feedOk=false\)\{[\s\S]*?(?=\nfunction renderHoldAlerts)/)?.[0];
 assert.ok(source,'pure private watch alert evaluator is available');
 const ctx={taipeiDateParts:()=>({year:'2026',month:'10',day:'14'}),tradingWindowAt:()=>true};
 vm.runInNewContext(source+';globalThis.evaluate=holdingAlertSignal;',ctx);
 const h={code:'2330',cost:100,shares:1000},m={price:91,quoteKind:'last_trade',quoteDay:'20261014'},q={valid:true},prefs={enabled:true,lossPct:8,gainPct:12,retracePct:5},now=new Date('2026-10-14T02:10:00Z');
 const run=(price=91,old=null,overrides={},valid=q,feed=true)=>ctx.evaluate(h,{...m,price,...overrides},valid,prefs,old,now,feed);
 assert.equal(run().signal.type,'loss','verified 9% drawdown must flag risk');
 assert.equal(run(93).signal,null,'within loss tolerance is not a signal');
 assert.equal(run(117).signal,null,'gains without pullback must not alert');
 const observed=run(121).peak;
 assert.equal(run(114,observed).signal.type,'retrace','observed peak pullback with profit qualification');
 assert.equal(run(120,observed).signal,null,'small pullback does not trigger');
 assert.equal(run(91,null,{quoteKind:'official_close'}).eligible,false);
 assert.equal(run(91,null,{quoteDay:'20261013'}).eligible,false);
 assert.equal(run(91,null,{}, {valid:false}).eligible,false);
 assert.equal(run(91,null,{}, q,false).eligible,false,'stale system feed blocks alert');
 ctx.tradingWindowAt=()=>false;assert.equal(run().eligible,false,'after hours blocks intraday notifications');
 ctx.tradingWindowAt=()=>true;assert.equal(ctx.evaluate({...h,cost:130},{...m,price:126},q,prefs,observed,now,true).signal,null,'changing cost resets stored peak');
 const disabled={...prefs,enabled:false};assert.equal(ctx.evaluate(h,m,q,disabled,null,now,true).eligible,false);
});
check('Private alert settings guard thresholds and persist only on the user device',()=>{
 const settings=html.match(/function normalizeHoldAlertPrefs\(input\)\{[\s\S]*?(?=\nfunction loadHoldAlertSettings)/)?.[0];
 const numeric=html.match(/function alertNumber\(x,min,max,fallback\)\{[^\n]+/)?.[0];
 assert.ok(settings&&numeric);
 const ctx={};vm.runInNewContext(numeric+'\n'+settings+';globalThis.normal=normalizeHoldAlertPrefs;',ctx);
 const invalid=ctx.normal({lossPct:-100,gainPct:999,retracePct:0,enabled:false});
 assert.equal(invalid.lossPct,8);assert.equal(invalid.gainPct,12);assert.equal(invalid.retracePct,5);assert.equal(invalid.enabled,false);
 assert.ok(html.includes("const HOLD_ALERT_SETTINGS_KEY='jei_hold_alert_prefs_v1'"));
 assert.ok(html.includes("const HOLD_ALERT_PEAKS_KEY='jei_hold_alert_peaks_v1'"));
 assert.ok(html.includes('if(!JEI_PRIVATE_APP)return;'));
 assert.ok(html.includes('holdAlertNotified[key]'),'alert toast throttled to one event per day/symbol/type');
 assert.ok(html.includes('id="alertLoss"')&&html.includes('id="alertGain"')&&html.includes('id="alertRetrace"'));
 assert.ok(html.includes("home.hidden=false")&&html.includes("renderHoldAlerts(rows)"));
});
check('Watchlist alerts never promise closed-app notifications or real orders',()=>{
 assert.ok(html.includes('Android 3.9.9 起支援作業系統定期背景風險通知'));
 assert.ok(html.includes('不是券商條件單'));
 assert.ok(html.includes("m?.quoteKind!=='last_trade'"));
 assert.ok(html.includes("!tradingWindowAt(now)"));
 assert.ok(html.includes('最高價為 App 觀察期間紀錄'));
});


check('Institutional rows are dated to their own source not intraday feed day',()=>{
 const source=html.match(/function institutionSnapshotDate\(inst,feed=system\)\{[\s\S]*?(?=\nfunction holdingMarketPressure)/)?.[0];
 assert.ok(source,'institutional source-date auditor exists');
 const ctx={isTrustedFeed:()=>true,system:{}};
 vm.runInNewContext(source+';globalThis.snapshot=institutionSnapshotDate;',ctx);
 const feed={source_data_date:'TWSE:1151013 / TPEx:1151014',data_date:'2026-10-14'};
 const tw=ctx.snapshot({source:'TWSE T86'},feed),tpex=ctx.snapshot({source:'TPEx institutional'},feed);
 assert.equal(tw.date,'2026-10-13');assert.equal(tw.fresh,false,"previous TWSE trades must not be presented as same-day selling");
 assert.equal(tpex.date,'2026-10-14');assert.equal(tpex.fresh,true,'same-day confirmed TPEx dataset can qualify');
 assert.equal(ctx.snapshot({source:'TWSE T86'}, {...feed,source_data_date:'TWSE:1150230'}).fresh,false,'calendar-invalid day rejected');
 assert.equal(ctx.snapshot({source:'unknown'},feed).fresh,false);
 ctx.isTrustedFeed=()=>false;assert.equal(ctx.snapshot({source:'TPEx institutional'},feed).fresh,false);
});
check('Market/sector/near-low risk ranking uses only verified current trade evidence',()=>{
 const source=html.match(/function holdingMarketPressure\(h,m,quality,feed,now=new Date\(\),verified=isTrustedFeed\(feed,now\)\)\{[\s\S]*?(?=\nfunction renderHoldingPressure)/)?.[0];
 assert.ok(source,'pure risk evidence evaluator exists');
 const ctx={taipeiDateParts:()=>({year:'2026',month:'10',day:'14'}),tradingWindowAt:()=>true,isTrustedFeed:()=>true};
 vm.runInNewContext(source+';globalThis.detect=holdingMarketPressure;',ctx);
 const h={code:'2330',name:'測試'},m={price:90,prev:100,high:107,low:89,quoteDay:'20261014',quoteKind:'last_trade'},q={valid:true};
 const feed={market:{mode:'盤中即時'},data_date:'2026-10-14',risk:{score:85},stock_sectors:{'2330':'AI族群'},sectors:[{name:'AI族群',score:35}]},now=new Date('2026-10-14T03:50:00Z');
 const run=(quote=m,qv=q,fd=feed,valid=true)=>ctx.detect(h,quote,qv,fd,now,valid);
 let risk=run();
 assert.equal(risk.eligible,true);assert.equal(risk.reasons.length,3);
 assert.equal(risk.priority,7);
 assert.equal(risk.reasons[0].kind,'near_low');
 assert.equal(risk.reasons[1].kind,'sector_weak');
 assert.equal(risk.reasons[2].kind,'market_confluence');
 assert.equal(run({...m,quoteKind:'official_close'}).eligible,false);
 assert.equal(run({...m,quoteDay:'20261013'}).eligible,false);
 assert.equal(run(m,{valid:false}).eligible,false);
 assert.equal(run(m,q,feed,false).eligible,false);
 ctx.tradingWindowAt=()=>false;assert.equal(run().eligible,false);ctx.tradingWindowAt=()=>true;
 assert.equal(run({...m,price:90,high:NaN,low:NaN}).reasons.length,2,'missing daily range cannot invent near-low selling pressure');
 assert.equal(run(m,q,{...feed,stock_sectors:{},sectors:[]}).reasons.length,2,'unknown industry must not be called weak');
 assert.equal(run(m,q,{...feed,sectors:[{name:'AI族群',score:null}]}).reasons.length,2,'missing industry score cannot masquerade as a zero-score selloff');
 assert.equal(run(m,q,{...feed,risk:{score:20},stock_sectors:{},sectors:[]}).reasons.length,1);
 assert.equal(run({...m,price:105},q,feed).reasons.length,0,'up stock is not marked as heavy selling');
 assert.equal(run(m,q,{...feed,market:{mode:'今日收盤'}}).eligible,false);
});
check('Intraday dashboard evidence and AI reject unsupported institutional exits',()=>{
 assert.ok(html.includes('id="pressurePanel"')&&html.includes('id="pressureList"')&&html.includes('id="quickPressure"'));
 assert.ok(html.includes('renderHoldingPressure(rows)'));
 assert.ok(html.includes('非逐筆即時資金流'));
 assert.ok(html.includes('法人資料截至 '));
 assert.ok(html.includes("const rawInst=(system.institutional||{})[h.code]||null"));
 assert.ok(html.includes("const code=stock.code,rawInst=(system.institutional||{})[code]||null"));
 assert.ok(html.includes("m?.quoteKind!=='last_trade'"));
 assert.ok(html.includes("m?.quoteKind==='official_close'&&(tradingWindow()||String(m.quoteDay)!==_today)"));
});


check('Android native background worker rejects stale feeds, quote substitutions and weekends',()=>{
 const fs=require('fs');
 const worker=fs.readFileSync('app/src/main/java/com/jei/stockradar/RiskWorker.java','utf8');
 const activity=fs.readFileSync('app/src/main/java/com/jei/stockradar/MainActivity.java','utf8');
 const gradle=fs.readFileSync('app/build.gradle','utf8');
 assert.ok(worker.includes('trustedLiveFeed(root, now)'));
 assert.ok(worker.includes('trustedExecutedTrade(quote, now)'));
 assert.ok(worker.includes('market.optBoolean("stale", true)'));
 assert.ok(worker.includes('market.opt("live_count")'),'background risk must inspect market breadth');
 assert.ok(worker.includes('((Number)liveCount).doubleValue() < 500'),'incomplete live snapshots cannot trigger Android risk events');
 assert.ok(activity.includes('public String testRiskNotification()'),'Android exposes a user-triggered notification diagnostic');
 assert.ok(activity.includes('nm.areNotificationsEnabled()'),'test notification respects OS notification setting');
 assert.ok(activity.includes('entry.put("type", "test")'),'test history never masquerades as a true stock alert');
 assert.ok(html.includes('onclick="testNativeRiskNotification()"'),'mobile hold page has notification diagnostic control');
 assert.ok(html.includes('id="nativeTestStatus"'),'manual notification feedback is visible');

 assert.ok(worker.includes('"盤中即時".equals(market.optString("mode", ""))'));
 assert.ok(worker.includes('lag <= 35L * 60L * 1000L'));
 assert.ok(worker.includes('lag <= 8L * 60L * 1000L'));
 assert.ok(worker.includes('Calendar.SATURDAY')&&worker.includes('Calendar.SUNDAY'));
 assert.ok(worker.includes('TimeZone.getTimeZone("Asia/Taipei")'));
 assert.ok(!worker.includes('(bid + ask) / 2.0'),'bid/ask midpoint cannot become last-execution price');
 assert.ok(!worker.includes('price = prev'),'previous close cannot become background alert price');
 assert.ok(worker.includes('prefs.getBoolean("bg_risk_enabled", true)'));
 assert.ok(worker.includes('"bg_hold_" + day + "_" + code'),'per-day per-stock deduping');
 assert.ok(worker.includes('new HashSet<>()'),'market exchange duplicates removed');
 assert.ok(worker.includes('recordRiskEvent(prefs, "holding"'));
 assert.ok(worker.includes('recordRiskEvent(prefs, "market"'));
 assert.ok(activity.includes('public String loadRiskEvents()'));
 assert.ok(activity.includes('public void setRiskNotificationEnabled(boolean enabled)'));
 const manifest=JSON.parse(fs.readFileSync('remote/update.json','utf8'));
 const code=gradle.match(/versionCode\s+(\d+)/);
 const name=gradle.match(/versionName\s+'([^']+)'/);
 assert.ok(code&&name,'Android version must be defined');
 assert.equal(Number(manifest.versionCode),Number(code[1]),'update manifest must match APK version code');
 assert.equal(String(manifest.versionName).split(/\s+/)[0],name[1],'update manifest must match APK version name');
 assert.ok(html.includes(`const UI_VERSION='${manifest.uiVersion}';`),'remote UI version must match update manifest');
});
check('Native history UI escapes risk titles and syncs opt-out with Android Worker',()=>{
 assert.ok(html.includes('id="nativeAlertHistory"'));
 assert.ok(html.includes('function renderNativeAlertHistory()'));
 assert.ok(html.includes("typeof JEINative.loadRiskEvents!=='function'"));
 assert.ok(html.includes("typeof JEINative.setRiskNotificationEnabled==='function'"));
 assert.ok(html.includes('row.append(stamp,title,detail)'));
 assert.ok(html.includes('title.textContent=String(x.title'));
 assert.ok(html.includes('detail.textContent=String(x.detail'));
 assert.ok(html.includes('renderNativeAlertHistory();'));
 assert.ok(html.includes('依工作排程與手機省電政策執行'));
});

check('Network recommendation success requires candidates',()=>assert.ok(py.includes('if not old_web_recommendations and old_web_status.get("ok"):')));

check('Intraday quotes cannot masquerade as official post-close',()=>{assert.ok(py.includes('if live_valid and market_open:'));assert.ok(py.includes('source_is_today=(latest_close_date is not None and not known_closure')&&py.includes('final_twse_dates=={latest_close_date}')&&py.includes('final_tpex_dates=={latest_close_date}'));assert.ok(py.includes('if official_close_verified:')&&py.includes('and not market_open and now.hour*60+now.minute>=810'));assert.ok(py.includes('fetch_latest_offhours_close'))});

check('TPEx close feed rejects partial responses',()=>{assert.ok(py.includes('len(unique)<500'));assert.ok(py.includes('coverage too low'));assert.ok(py.includes('return list(unique.values())'))});
if(passed+failed<30){console.error('FAIL expected at least 30 independent checks');process.exitCode=1;}
console.log(`JEI smoke summary: ${passed}/${passed+failed} passed (${Math.round(100*passed/(passed+failed))}%)`);


