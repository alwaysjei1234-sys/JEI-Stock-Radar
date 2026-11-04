const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs/promises');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const fixture={schema:1,mode:'forward_official_close_pick_validation',updated_at:'fixture',latest_official_day:'2026-11-04',total_frozen_picks:2,
 groups:{monster:{'3':{completed:1,pending:0,missing_price:0,corporate_action_unadjusted:1,win_rate_pct:0,avg_estimated_net_pct:-1,median_estimated_net_pct:-1,worst_estimated_net_pct:-1}}},
 picks:[{id:'a',day:'2026-10-22',group:'monster',rank:1,code:'3691',name:'合成除權測試',score:86,signal_close:109,
 outcomes:[{trading_days:3,status:'corporate_action_unadjusted',end_day:'2026-10-29',events:[{day:'2026-10-27',note:'除權'}]}]},
 {id:'b',day:'2026-10-22',group:'monster',rank:2,code:'1000',name:'合成已完成樣本',score:80,signal_close:100,
 outcomes:[{trading_days:3,status:'complete',end_day:'2026-10-29',estimated_net_return_pct:-1}]}],analysis_notes:[]};
const server=http.createServer(async(req,res)=>{
 try{
  const pathname=new URL(req.url,'http://localhost').pathname;
  if(pathname==='/remote/pick_validation.json'){res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(fixture));return}
  const target=path.resolve(root,'.'+pathname);if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return}
  res.writeHead(200,{'Content-Type':target.endsWith('.js')?'application/javascript':target.endsWith('.json')?'application/json':'text/html; charset=utf-8'}).end(await fs.readFile(target));
 }catch{res.writeHead(404).end()}
});
async function run(){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
 try{
  browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
  const p=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto('http://127.0.0.1:'+server.address().port+'/remote/pick_validation.html',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>document.querySelector('#total').textContent==='2');
  await p.locator('#group').selectOption('monster');
  assert.match(await p.locator('#comparison').innerText(),/除權息待調整 1 筆/);
  assert.equal(await p.locator('#sample').innerText(),'1');
  const row=p.locator('#pickRows tr').filter({hasText:'3691'});
  assert.match(await row.innerText(),/除權息待調整/);assert.match(await row.innerText(),/不計勝負/);
  assert.ok(!(await row.innerText()).includes('未到期'));
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  await p.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:')?route.continue():route.abort());
  await p.goto('http://127.0.0.1:'+server.address().port+'/remote/index.html',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>document.querySelector('#jeiPickOverview').textContent.includes('除權息待調整 1 項次'));
  assert.ok(!(await p.locator('#jeiPickSync').innerText()).includes('資料同步失敗'));
  assert.deepEqual(errors,[]);
  console.log('PASS 390px corporate-action page: preserved sample, explicit adjustment status, no invented return and no overflow');
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve))}
}
run().catch(e=>{console.error(e);process.exitCode=1});
