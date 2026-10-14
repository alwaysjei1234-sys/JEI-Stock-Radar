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
  await page.route('https://jei-stock-radar.vercel.app/api/consult**',route=>route.fulfill({
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
  const privatePage=await privateContext.newPage(),privateErrors=[];
  privatePage.on('pageerror',error=>privateErrors.push(error.message));
  await privatePage.addInitScript(()=>{
   window.JEINative={
    loadHoldings:()=>JSON.stringify([{code:'2330',name:'測試持股',cost:100,shares:1000}]),
    saveHoldings:()=>{},loadSetting:()=>'',saveSetting:()=>{},getAppVersion:()=>'test',
    getAppVersionCode:()=>32,isOnline:()=>true,refreshSystem:()=>{},refreshMarketData:()=>{},
    fetchStaticJson:()=>{},checkForUpdates:()=>{},refreshRemoteUI:()=>{},consultAI:()=>{},openUrl:()=>{}
   };
  });
  await privatePage.goto('file://'+path.join(ROOT,'remote','index.html'),{waitUntil:'domcontentloaded'});
  await privatePage.evaluate(()=>{go('hold')});
  await privatePage.locator('#holdAlertPanel').waitFor({state:'visible'});
  assert.equal(await privatePage.locator('#alertLoss').inputValue(),'8','native watch alert defaults to 8% loss');
  assert.equal(await privatePage.locator('#alertGain').inputValue(),'12');
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
  console.log('PASS private Android-like portfolio alerts and official-close suppression');

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

  await page.goto(base+'paper.html',{waitUntil:'domcontentloaded'});
  await page.locator('h1').waitFor({state:'visible'});
  assert.match(await page.locator('h1').innerText(),/當沖/);
  console.log('PASS mobile day-trading simulation page is separate');
  assert.deepEqual(errors,[],'uncaught browser JavaScript errors');
  }finally{await browser.close()}
}
run().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{await close()});
