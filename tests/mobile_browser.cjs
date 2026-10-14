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
  assert.match(await page.locator('#feedGate').innerText(),/行情|收盤/);
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
  await browser.close();
}
run().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{await close()});
