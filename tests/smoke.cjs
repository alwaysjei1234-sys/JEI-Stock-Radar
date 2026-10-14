const fs=require('node:fs');const assert=require('node:assert/strict');const html=fs.readFileSync('remote/index.html','utf8');const paper=fs.readFileSync('remote/paper.html','utf8');const py=fs.readFileSync('scripts/update_system.py','utf8');const manifest=fs.readFileSync('app/src/main/AndroidManifest.xml','utf8');const activity=fs.readFileSync('app/src/main/java/com/jei/stockradar/MainActivity.java','utf8');
let passed=0,failed=0;
function check(label,fn){try{fn();passed++;console.log('PASS',label)}catch(e){failed++;console.error('FAIL',label,e.stack||e.message);process.exitCode=1}}
check('Public page guards private routes',()=>{assert.match(html,/function go\(id\)\{if\(!JEI_PRIVATE_APP/);assert.match(html,/function loadHoldings\(\)\{if\(!JEI_PRIVATE_APP/)});
check('No public portfolio nodes removed (prevents JS null dereference)',()=>assert.doesNotMatch(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>el\.remove\(\)\)/));
check('Public feed strips private positions',()=>{assert.match(py,/if out\.get\("holdings"\):/);assert.match(html,/system\.holdings=JEI_PRIVATE_APP\?/)});
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
check('Android backups disabled',()=>assert.match(manifest,/android:allowBackup="false"/));
check('WebView file-origin crossing disabled',()=>{assert.match(activity,/setAllowFileAccessFromFileURLs\(false\)/);assert.match(activity,/setAllowUniversalAccessFromFileURLs\(false\)/)});
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
 let captured=[],trusted=true;const ctx={isTrustedFeed:()=>trusted,system:{attack:[{code:'1111',score:90,sector:'AI',price:100,change_pct:3},{code:'2222',score:60,sector:'AI',price:90,change_pct:2},{code:'3333',score:95,sector:'航運',price:70,change_pct:2},{code:'4444',score:99,sector:'AI',price:500,change_pct:4}],market:{mode:'今日收盤'},data_date:'2026-10-13'},$:id=>els[id],renderRank:(_id,arr)=>{captured=arr},updateFeedFreshness:()=>{},syncScreenSectors:()=>{}};
 vm.runInNewContext(fn+';globalThis.testScreen=renderAttackScreener;',ctx);ctx.testScreen();assert.equal(captured.length,1);assert.equal(captured[0].code,'1111');
 ctx.system.market.mode='盤中資料不足';trusted=false;ctx.testScreen();assert.equal(captured.length,0);
});

check('Feed freshness rejects old, stale, or mislabeled intraday quotes',()=>{
 const line=html.match(/^function isTrustedFeed\(.*$/m)?.[0];assert.ok(line);
 const ctx={};vm.runInNewContext(line+';globalThis.verify=isTrustedFeed;',ctx);
 const day=new Date('2026-10-14T02:00:00Z');
 const ok={updated_at:'2026-10-14 10:00',data_date:'2026-10-14',market:{mode:'盤中即時',stale:false,live_valid:true,close_count:1900}};
 assert.equal(ctx.verify(ok,day),true);
 assert.equal(ctx.verify({...ok,data_date:'2026-10-13'},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,stale:true}},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,mode:'資料過期'}},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,live_valid:false}},day),false);
 assert.equal(ctx.verify({...ok,market:{...ok.market,mode:'今日收盤',live_valid:false}},day),true);
 assert.equal(ctx.verify({...ok,market:{...ok.market,mode:'今日收盤',close_count:0}},day),false);
 assert.equal(ctx.verify({...ok,updated_at:'2026-10-14 09:00'},day),false,'old but same-day intraday feed must fail');
 assert.equal(ctx.verify({...ok,updated_at:'2026-10-14 10:05'},day),false,'future feed timestamp must fail');
});
check('Exchange quote dates and 13:30 close boundary are enforced',()=>{
 assert.ok(py.includes('if quote_day!=expected_day:continue'));
 assert.ok(py.includes('540<=minutes<810'));
 assert.ok(py.includes('live_valid=market_open and live_count>=500'));
 assert.ok(py.includes('market_mode="資料過期" if stale_source'));
 assert.ok(html.includes('liveBad=!isTrustedFeed()'));
 assert.ok(html.includes("arr=[];empty='今日有效行情未驗證"),'all radar lists must halt on stale data');
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

check('Paper scanner is read-only and halts on insufficient market coverage',()=>{assert.ok(paper.includes("readJeiStatic('system')"));assert.ok(paper.includes("halted=feed.market?.mode==='盤中資料不足'"));assert.ok(paper.includes("if(halted||!valid)return"));assert.doesNotMatch(paper,/\/api\/orders|placeOrder\(/);assert.ok(paper.includes('JEINative.fetchStaticJson(kind)'))});
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
 const make=mode=>({data_date:'2026-10-13',updated_at:'2026-10-13 10:00',market:{stale:false,mode,live_valid:true}});
 assert.equal(ctx.mode(make('資料過期'),now),'');
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
 const funcs=html.split('\n').filter(x=>/^(function taipeiDateParts\(|function tradingWindowAt\(|function tradingWindow\(|function holdingQuoteQuality\()/.test(x)).join('\n');
 const ctx={Intl};vm.runInNewContext(funcs+';globalThis.inspect=holdingQuoteQuality;',ctx);
 const during=new Date('2026-10-14T02:10:00Z'),post=new Date('2026-10-14T05:35:00Z');
 const mk=(minute=605,received='2026-10-14T02:07:00Z')=>({quoteDay:'20261014',quoteKind:'last_trade',quoteMinute:minute,receivedAt:Date.parse(received)});
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
check('Cloud return and drawdown reporting is explicit',()=>{
 assert.ok(cash.includes('<th>估算總報酬</th><th>最大回撤</th>'));
 assert.ok(cash.includes('s.max_drawdown_pct'));
 assert.ok(cash.includes('Number(s.estimated_liquidation_equity_ntd)/basis-1'));
});

check('Network recommendation success requires candidates',()=>assert.ok(py.includes('if not old_web_recommendations and old_web_status.get("ok"):')));

check('Intraday quotes cannot masquerade as official post-close',()=>{assert.ok(py.includes('if live_valid and market_open:'));assert.ok(py.includes('source_is_today=twse_today and tpex_today'));assert.ok(py.includes('if source_is_today and not market_open and now.hour >= 13:'))});

if(passed+failed<30){console.error('FAIL expected at least 30 independent checks');process.exitCode=1;}
console.log(`JEI smoke summary: ${passed}/${passed+failed} passed (${Math.round(100*passed/(passed+failed))}%)`);
