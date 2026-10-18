const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require('playwright');

const ROOT=path.resolve(__dirname,'..');
const MIME={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.js':'application/javascript; charset=utf-8'};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  let decoded;
  try{decoded=decodeURIComponent(url.pathname)}catch{res.writeHead(400).end();return}
  const target=path.resolve(ROOT,'.'+decoded);
  if(!target.startsWith(ROOT+path.sep)){res.writeHead(403).end();return}
  try{
    const bytes=await fs.readFile(target);
    res.writeHead(200,{'Content-Type':MIME[path.extname(target)]||'text/plain','Cache-Control':'no-store'});
    res.end(bytes);
  }catch{res.writeHead(404).end()}
});
function listen(){return new Promise(resolve=>server.listen(0,'127.0.0.1',()=>resolve(server.address().port)))}
function close(){return new Promise(resolve=>server.close(resolve))}
async function run(){
  const port=await listen(),base='http://127.0.0.1:'+port+'/remote/';
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  try{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('https://jei-stock-radar.vercel.app/api/consult**',route=>route.request().method()==='POST'?
    route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,verified:true,free_only:true})}):
    route.fulfill({
    status:200,contentType:'application/json',
    body:JSON.stringify({ok:true,free_only:true,paid_gateway:false,providers:{
      groq_oss:{label:'GPT-OSS 120B',server_key:true,model:'test-free'},
      gemini_free:{server_key:false},groq_qwen:{server_key:true},openrouter_free:{server_key:false}
    }})
  }));

  await page.goto(base+'index.html',{waitUntil:'domcontentloaded'});
  await page.locator('#riskBox').waitFor({state:'visible'});
  await page.locator('#homeQuick').waitFor({state:'visible'});
  await page.locator('#feedGate').waitFor({state:'visible'});
  assert.match(await page.locator('#feedGate').innerText(),/行情|收盤|盤中/);
  assert.match(await page.locator('#quickRisk').innerText(),/大盤/);
  assert.match(await page.locator('#quickHold').innerText(),/Android App/);
  assert.match(await page.locator('#quickAttack').innerText(),/主攻/);
  assert.equal(await page.locator('#holdTriage').isVisible(),false,'private triage never shown on public browser');
  assert.equal(await page.locator('#holdToolbar').isVisible(),false,'private sort/filter controls never shown on public browser');
  assert.equal(await page.locator('#privateRotate').isVisible(),false,'private rotation comparison never shown on public browser');
  await page.waitForFunction(()=>document.querySelector('#sysStatus').textContent.includes('feed 已連線'),{timeout:15000});
  assert.equal(await page.locator('#hold').isVisible(),false,'personal holdings never exposed on public browser');
  // Weekend/holiday research is visible and dated, but no historical trade levels.
  await page.locator('[data-go="attack"]').first().click();
  await page.evaluate(()=>{
    window.__weekendSystemBefore=system;
    window.__weekendTrustedBefore=isTrustedFeed;
    window.__weekendArchiveBefore=isRecentCloseObservation;
    system={...system,
      data_date:'2026-10-16',updated_at:'2026-10-16 17:10',
      market:{mode:'今日收盤',stale:false,close_count:1954},
      attack:[{code:'2344',name:'歷史範例股',sector:'測試族群',score:95,price:50,change_pct:5,
        reason:'前次驗證收盤',entry_low:47,entry_high:50,defense:44,target1:55,target2:60}],
      sectors:[{name:'測試族群',score:80,avg_pct:3.5,breadth:67,value_billion:20,leaders:[]}],
      patterns:{data_date:'2026-10-16',status:'ready',coverage:1000,signals:{
        breakout:[{code:'2344',name:'歷史範例股',score:90,price:50}],bollinger:[],vcp:[],sector:[]}}
    };
    if(!window.__weekendArchiveBefore(system,new Date('2026-10-17T23:29:00Z')))
      throw Error('verified Friday close must be readable on Sunday');
    if(window.__weekendTrustedBefore(system,new Date('2026-10-17T23:29:00Z')))
      throw Error('Friday close must not be trusted as Sunday actionable quotes');
    window.isTrustedFeed=()=>false;
    window.isRecentCloseObservation=feed=>window.__weekendArchiveBefore(feed||system,new Date('2026-10-17T23:29:00Z'));
    $('screenScore').value='0';
    renderAttackScreener();renderSectors();renderPatternRadar();
  });
  assert.match(await page.locator('#attackList').innerText(),/歷史收盤觀察榜/);
  assert.match(await page.locator('#attackList').innerText(),/2344 歷史範例股/);
  assert.doesNotMatch(await page.locator('#attackList').innerText(),/參考區|防守 44|目標 55/);
  assert.match(await page.locator('#sectorTop').innerText(),/2026-10-16.*歷史參考/);
  await page.evaluate(()=>{system.market.stale=true;renderAttackScreener();});
  assert.doesNotMatch(await page.locator('#attackList').innerText(),/歷史範例股/);
  await page.evaluate(()=>{
    system=window.__weekendSystemBefore;
    window.isTrustedFeed=window.__weekendTrustedBefore;
    window.isRecentCloseObservation=window.__weekendArchiveBefore;
    $('screenScore').value='75';
    renderSystem();
  });
  console.log('PASS weekend archive UI: historical names visible, live trade levels hidden, stale blocked');

  // The credential form must be usable on phones; verify without any real model call.
  await page.locator('[data-go="settings"]').first().click();
  await page.locator('#settings').waitFor({state:'visible'});
  await page.locator('#aiBackendToken').fill('ci-only-private-token');
  await page.getByRole('button',{name:'儲存連線碼'}).click();
  await page.getByRole('button',{name:'測試連線碼'}).click();
  await page.waitForFunction(()=>document.querySelector('#aiTokenStatus').textContent.includes('已驗證'));
  assert.match(await page.locator('#aiTokenStatus').innerText(),/已驗證/);
  console.log('PASS usable JEI private AI token settings and model-free authorization');
  await page.locator('[data-go="patterns"]').first().click();
  await page.locator('#patterns').waitFor({state:'visible'});
  // Force a deterministic unpublished snapshot; the real daily feed may already be ready.
  await page.evaluate(()=>{system.patterns={status:'insufficient',data_date:system.data_date,signals:{}};renderPatternRadar()});
  assert.match(await page.locator('#patternStatus').innerText(),/尚未可用/,'unpublished strategy feed must not invent candidates');
  await page.evaluate(()=>{
   const d=taipeiDateParts(),today=d.year+'-'+d.month+'-'+d.day;
   // Presentation fixture is deliberately independent of the real current clock;
   // the exchange-close and coverage guard is exercised by deterministic smoke cases.
   window.__trustedFeedBeforeFixture=isTrustedFeed;
   window.isTrustedFeed=feed=>feed?.market?.stale===false&&feed?.market?.mode==='今日收盤'&&Number(feed.market.close_count)>=500;
   system.data_date=today;
   system.market={mode:'今日收盤',stale:false,close_count:1950};
   system.patterns={data_date:today,status:'ready',coverage:1300,signals:{
    breakout:[{code:'2305',name:'測試個股',score:82,price:25,change_pct:2,sector:'測試',reason:'突破測試'}],
    bollinger:[],vcp:[],sector:[]
   }};
   renderPatternRadar();
  });
  assert.match(await page.locator('#patternResults').innerText(),/2305 測試個股/);
  await page.locator('[data-pattern="vcp"]').click();
  assert.match(await page.locator('#patternResults').innerText(),/沒有達標候選/);
  await page.evaluate(()=>{system.market.stale=true;renderPatternRadar()});
  assert.doesNotMatch(await page.locator('#patternResults').innerText(),/2305 測試個股/,'stale feed suppresses strategy results');
  assert.match(await page.locator('#patternStatus').innerText(),/尚未可用/);
  await page.evaluate(()=>{window.isTrustedFeed=window.__trustedFeedBeforeFixture});
  console.log('PASS dated four-strategy radar, switching, no-result and stale suppression');
  await page.locator('[data-go="attack"]').first().click();
  await page.locator('#attack').waitFor({state:'visible'});
  await page.locator('[data-go="chat"]').last().click();
  await page.locator('#chat').waitFor({state:'visible'});
  await page.locator('#chatBox').fill('大盤風險');
  await page.locator('#chatSendBtn').click();
  await page.waitForFunction(()=>document.querySelectorAll('#chatLog .chatMsg.bot').length>=2);
  assert.equal(await page.locator('#chatSendBtn').isEnabled(),true);
  console.log('PASS mobile dashboard, public privacy, screener and local AI chat');

  // Android-WebView-like private fixture: file origin + native bridge, no public portfolio upload.
  const privateContext=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  await privateContext.setOffline(true);
  const privatePage=await privateContext.newPage(),privateErrors=[];
  privatePage.on('pageerror',error=>privateErrors.push(error.message));
  await privatePage.addInitScript(()=>{
   window.JEINative={
    loadHoldings:()=>JSON.stringify([{code:'2330',name:'測試持股',cost:100,shares:1000}]),
    saveHoldings:()=>{},loadSetting:()=>'',saveSetting:()=>{},getAppVersion:()=>'test',
    getAppVersionCode:()=>36,isOnline:()=>false,refreshSystem:()=>{},refreshMarketData:(codes)=>{window.__scanRequest=JSON.parse(codes);},
    loadRiskEvents:()=>JSON.stringify([{at:'2026-10-14 11:51',type:'holding',title:'JEI 持股盤中風險',detail:'測試 2330｜成交價已驗證'}]),
    testRiskNotification:()=>{window.__testedNativeNotice=true;return '已要求 Android 顯示測試通知，請查看手機通知欄';},
    getRiskNotificationEnabled:()=>window.__nativeRiskEnabled!==false,
    setRiskNotificationEnabled:(enabled)=>{window.__nativeRiskEnabled=enabled;},
    fetchStaticJson:()=>{},checkForUpdates:()=>{},refreshRemoteUI:()=>{},consultAI:()=>{},openUrl:()=>{}
   };
  });
  await privatePage.goto('file://'+path.join(ROOT,'app','src','main','assets','index.html'),{waitUntil:'domcontentloaded'});
  assert.match(await privatePage.locator('#uiVer').innerText(),/3\.9\.12/,'offline asset includes prioritised quotes and ETF support');
  await privatePage.evaluate(()=>{go('hold')});
  await privatePage.locator('#holdAlertPanel').waitFor({state:'visible'});
  assert.equal(await privatePage.locator('#alertLoss').inputValue(),'8','native watch alert defaults to 8% loss');
  assert.equal(await privatePage.locator('#alertGain').inputValue(),'12');
  assert.match(await privatePage.locator('#nativeAlertHistory').textContent(),/JEI 持股盤中風險/);
  assert.match(await privatePage.locator('#nativeAlertHistory').textContent(),/2026-10-14 11:51/);
  await privatePage.locator('#nativeEventPanel').evaluate(el=>el.open=true);
  await privatePage.getByRole('button',{name:'測試手機通知'}).click();
  assert.equal(await privatePage.evaluate(()=>window.__testedNativeNotice),true,'manual diagnostic reaches native bridge');
  assert.match(await privatePage.locator('#nativeTestStatus').innerText(),/已要求 Android 顯示測試通知/);
  console.log('PASS Android native notification manual diagnostic and visible feedback');
  await privatePage.evaluate(()=>{
    // Synthetic ETF, not any user's real private holdings.
    holdings.push({code:'00988B',name:'合成測試債券 ETF',cost:16,shares:1000});
    system.universe=Array.from({length:1900},(_,i)=>({code:String(1000+i)}));
    system.attack=[{code:'2344',name:'測試候選',score:91,price:25}];
    window.tradingWindow=()=>true;
    refreshMarket();
  });
  const requested=await privatePage.evaluate(()=>window.__scanRequest);
  assert.equal(requested[0],'2330','held shares must be prioritised');
  assert.equal(requested[1],'00988B','held bond ETF must be prioritised');
  assert.ok(requested.includes('2344'),'cloud selected candidates are also scanned');
  assert.ok(requested.length<=240,'phone must not fetch all 1900 symbols');
  console.log('PASS Android stock-first bounded quote requests preserve ETF symbol');
  await privatePage.locator('#alertSettings').evaluate(el=>el.open=true);
  await privatePage.locator('#alertEnabled').uncheck();
  await privatePage.getByRole('button',{name:'儲存本機警戒設定'}).click();
  assert.equal(await privatePage.evaluate(()=>window.__nativeRiskEnabled),false,'screen risk toggle must disable native worker');
  await privatePage.locator('#alertEnabled').check();
  await privatePage.getByRole('button',{name:'儲存本機警戒設定'}).click();
  assert.equal(await privatePage.evaluate(()=>window.__nativeRiskEnabled),true,'re-enable background risk worker');
  await privatePage.evaluate(()=>{
   window.isTrustedFeed=()=>true;window.tradingWindowAt=()=>true;
   window.holdingQuoteQuality=()=>({valid:true,label:'測試有效成交'});
   const p=taipeiDateParts(),day=p.year+p.month+p.day;
   system.market={mode:'盤中即時'};system.risk={score:85};system.stock_sectors={'2330':'AI族群'};system.sectors=[{name:'AI族群',score:35}];
   market['2330']={price:91,prev:100,high:107,low:89,quoteDay:day,quoteKind:'last_trade',quoteMinute:700,receivedAt:Date.now()};
   renderHoldings();
  });
  assert.match(await privatePage.locator('#holdAlertList').innerText(),/虧損警戒/);
  assert.match(await privatePage.locator('#quickAlert').innerText(),/盤中警戒 1 檔/);
  assert.match(await privatePage.locator('#pressureList').innerText(),/跌幅擴大且接近日低/);
  assert.match(await privatePage.locator('#pressureList').innerText(),/族群同步偏弱/);
  assert.match(await privatePage.locator('#pressureList').innerText(),/大盤風險共振/);
  assert.match(await privatePage.locator('#quickPressure').innerText(),/弱勢訊號 1 檔/);
  await privatePage.evaluate(()=>{market['2330'].quoteKind='official_close';renderHoldings()});
  assert.doesNotMatch(await privatePage.locator('#holdAlertList').innerText(),/虧損警戒/,'archive close may not trigger in-app alerts');
  assert.doesNotMatch(await privatePage.locator('#pressureList').innerText(),/跌幅擴大且接近日低/,'archive closes cannot trigger intraday pressure');
  assert.deepEqual(privateErrors,[],'native watchlist fixture has no uncaught JavaScript errors');
  await privateContext.close();
  console.log('PASS offline Android bundled UI, private risk alerts and official-close suppression');

  await page.goto(base+'industry_research.html',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('來源審核基準日'),{timeout:12000});
  assert.match(await page.locator('h1').innerText(),/未來主流產業/);
  assert.match(await page.locator('#themes').innerText(),/記憶體\/儲存/);
  assert.match(await page.locator('#themes').innerText(),/多機構產業研究佐證/);
  assert.match(await page.locator('#themes').innerText(),/單一研究機構佐證/);
  assert.match(await page.locator('#themes').innerText(),/研究證據不足/);
  assert.match(await page.locator('#themes').innerText(),/產業展望仍未完成逐家公司基本面驗證/);
  assert.ok((await page.locator('#themes a[href^="https://"]').count())>=5,
            'research scorecard must have direct dated primary source links');
  assert.equal(await page.locator('#themes script').count(),0,
               'research report source strings must not be executable markup');
  console.log('PASS industry research cross-validation: independent sources, dates, caution and no fabricated stock buy');

  await page.goto(base+'cash.html',{waitUntil:'domcontentloaded'});
  await page.locator('#cloudRows tr').first().waitFor({state:'attached',timeout:15000});
  assert.equal(await page.locator('#cloudRows tr').count(),4);
  assert.equal(await page.locator('#cloudRows tr').first().locator('td').count(),8,'cloud scorecard reports return and drawdown');
  assert.match(await page.locator('#cloudCompare').innerText(),/暫不排名|四策略比較/,'cloud status must state if sample is sufficient');
  assert.match(await page.locator('#cloudKpiStatus').innerText(),/樣本不足|可比較/);
  assert.match(await page.locator('#cloudKpiLeader').innerText(),/暫不排名|固定|移動/);
  assert.match(await page.locator('#cloudStatus').innerText(),/2026-10-13|更新交易日/);
  await page.locator('#scan').click();
  await page.waitForFunction(()=>!document.querySelector('#scanStatus').textContent.includes('尚未載入'));
  console.log('PASS mobile cash page, cloud 4-strategy scoreboard and stock scanning');

  // Stock picking must keep as-of selections immutable, flag incomplete horizons,
  // and never execute candidate labels as untrusted HTML.
  await page.route('**/pick_validation.json?**',route=>route.fulfill({
   status:200,contentType:'application/json',body:JSON.stringify({
    schema:1,mode:'forward_official_close_pick_validation',
    latest_official_day:'2026-10-16',updated_at:'2026-10-18 08:10',
    total_frozen_picks:2,analysis_notes:['不可事後補選贏家'],
    groups:{attack:{
     '3':{completed:1,pending:1,missing_price:0,win_rate_pct:100,avg_estimated_net_pct:5.52,median_estimated_net_pct:5.52,worst_estimated_net_pct:5.52},
     '7':{completed:0,pending:2,missing_price:0,win_rate_pct:null,avg_estimated_net_pct:null,median_estimated_net_pct:null,worst_estimated_net_pct:null}
    }},
    picks:[
     {day:'2026-10-16',group:'attack',rank:1,code:'3017',name:'測試〈script〉',score:95,signal_close:3315,
      outcomes:[{trading_days:3,status:'complete',end_day:'2026-10-21',estimated_net_return_pct:5.52},{trading_days:7,status:'pending'}]},
     {day:'2026-10-16',group:'attack',rank:2,code:'6531',name:'待觀察',score:90,signal_close:882,
      outcomes:[{trading_days:3,status:'pending'},{trading_days:7,status:'pending'}]}
    ]
   })
  }));
  await page.goto(base+'pick_validation.html',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('最後報告更新'));
  assert.equal(await page.locator('#asOf').innerText(),'2026-10-16');
  assert.equal(await page.locator('#total').innerText(),'2');
  assert.match(await page.locator('#comparison').innerText(),/有效樣本少於10筆/);
  assert.match(await page.locator('#pickRows').innerText(),/5.52%/);
  assert.equal(await page.locator('#pickRows script').count(),0,'untrusted pick names are text only');
  await page.locator('#horizon').selectOption('7');
  assert.equal(await page.locator('#sample').innerText(),'0');
  assert.equal(await page.locator('#wins').innerText(),'--');
  assert.match(await page.locator('#pickRows').innerText(),/尚待第 7 個交易日/);
  console.log('PASS forward-only pick validation scorecard: 3-day complete, 7-day pending, no HTML injection');

  await page.goto(base+'paper.html',{waitUntil:'domcontentloaded'});
  await page.locator('h1').waitFor({state:'visible'});
  assert.match(await page.locator('h1').innerText(),/當沖/);
  console.log('PASS mobile day-trading simulation page is separate');
  assert.deepEqual(errors,[],'uncaught browser JavaScript errors');
  }finally{await browser.close()}
}
run().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{await close()});
