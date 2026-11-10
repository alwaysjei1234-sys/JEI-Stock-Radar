// Mobile UI regression; fixtures never contact LINE or send a message.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs/promises');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const server=http.createServer(async(req,res)=>{
 try{
  const pathname=new URL(req.url,'http://localhost').pathname;
  const target=path.resolve(root,'.'+pathname);
  if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return}
  const data=await fs.readFile(target);
  res.writeHead(200,{'Content-Type':target.endsWith('.json')?'application/json':'text/html; charset=utf-8'});res.end(data);
 }catch{res.writeHead(404).end()}
});
async function run(){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
  browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
  const p=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.clock.setFixedTime(new Date('2026-11-05T01:10:00+08:00'));
  const record={date:'2026-11-04',edition:'close',checked_at:'2026-11-04T19:15:51+08:00',status:'accepted',evidence_url:'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/123'};
  let recordStatus=200,policyChecks={};
  await p.route('**/line_status.json*',route=>route.fulfill({status:recordStatus,contentType:'application/json',body:JSON.stringify({schema:1,editions:{close:record},policy_checks:policyChecks})}));
  await p.route('**/brief.json*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({schema:1,close:{date:'2026-11-04',status:'ready',blocks:[{title:'測試摘要',items:['公開行情測試資料']}]}})}));
  await p.goto('http://127.0.0.1:'+server.address().port+'/remote/brief.html',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>document.querySelector('#line-status').textContent.includes('尚無可核對'));
  await p.locator('#close').click();
  await p.waitForFunction(()=>document.querySelector('#line-status').textContent.includes('歷史紀錄'));
  assert.match(await p.locator('#line-status').innerText(),/API 已接受.*手機實收尚未確認/);
  assert.match(await p.locator('#line-evidence').getAttribute('href'),/\/123$/);
  assert.ok(await p.locator('#content section').count()>0);
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  Object.assign(record,{date:'2026-11-05',checked_at:'2026-11-05T01:09:00+08:00',status:'quota_blocked',evidence_url:'javascript:alert(1)'});
  await p.locator('#reload').click();
  await p.waitForFunction(()=>document.querySelector('#line-status').textContent.includes('今日紀錄'));
  assert.match(await p.locator('#line-status').innerText(),/免費額度安全檢查未通過/);
  assert.ok(await p.locator('#line-evidence').isHidden());
  record.accepted_attempt={date:record.date,edition:'close',checked_at:'2026-11-05T00:59:00+08:00',status:'accepted',http_status:200,evidence_url:'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/123',token:'SECRET'};
  await p.locator('#reload').click();
  await p.waitForFunction(()=>document.querySelector('#line-status').textContent.includes('先前已獲 API 接受'));
  assert.match(await p.locator('#line-status').innerText(),/免費額度安全檢查未通過.*先前已獲 API 接受.*手機實收尚未確認/);
  assert.ok(!(await p.locator('#line-status').innerText()).includes('SECRET'));
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  policyChecks.close={record_kind:'policy_check',date:'2026-11-05',edition:'close',checked_at:'2026-11-05T01:09:30+08:00',status:'policy_skipped',policy_code:'dispatch_window_not_open',evidence_url:'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/456',reason:'SECRET'};
  await p.locator('#reload').click();
  await p.waitForFunction(()=>document.querySelector('#line-status').textContent.includes('本次未發送'));
  assert.match(await p.locator('#line-status').innerText(),/免費額度安全檢查未通過.*先前已獲 API 接受.*本日發送時段未開始.*不是 API 發送嘗試/);
  assert.equal(await p.locator('#line-evidence').getAttribute('href'),policyChecks.close.evidence_url);
  assert.ok(!(await p.locator('#line-status').innerText()).includes('SECRET'));
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  policyChecks.close.policy_code='SECRET';
  await p.locator('#reload').click();
  await p.waitForFunction(()=>!document.querySelector('#line-status').textContent.includes('排程檢查'));
  assert.ok(await p.locator('#line-evidence').isHidden());
  recordStatus=503;await p.locator('#reload').click();
  await p.waitForFunction(()=>document.querySelector('#line-status').textContent.includes('尚無可核對'));
  assert.ok(await p.locator('#content section').count()>0,'diagnostic failure must not hide the valid report');
  assert.deepEqual(errors,[]);
  console.log('PASS 390px mobile LINE status: dated evidence, missing record, current quota block, safe link, outage isolation and no overflow');
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve))}
}
run().catch(error=>{console.error(error);process.exitCode=1});
