const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const now=new Date('2026-11-04T10:00:00+08:00');
for(const path of ['remote/index.html','app/src/main/assets/index.html']){
 const html=fs.readFileSync(path,'utf8'),code=html.slice(html.indexOf('function freshPartialQuotes('),html.indexOf('function isTrustedFeed('));
 assert.ok(code.includes('function renderPartialQuotes('));
 const elements={},ctx={Date,Intl,$:id=>elements[id]??={textContent:'',hidden:true}};
 vm.createContext(ctx);vm.runInContext(code+';globalThis.api={rows:freshPartialQuotes,render:renderPartialQuotes};',ctx);
 const quote={code:'6150',price:72.9,quote_time:'2026-11-04 09:59:00',cost:123,shares:999};
 const feed={data_date:'2026-11-03',universe:[{code:'6150',name:'<img src=x onerror=alert(1)>'}],market:{live_valid:false,no_new_picks:true,partial_live:{complete:false,quotes:[quote]}}};
 assert.equal(ctx.api.rows(feed,now).length,1,'today partial quote can coexist with yesterday close');
 assert.deepEqual(Object.keys(ctx.api.rows(feed,now)[0]).sort(),['code','name','price','quote_time']);
 for(const change of [{price:NaN},{price:Infinity},{price:true},{price:0},{price:'72.9'},{code:'<script>'},{quote_time:'2026-11-03 09:59:00'},{quote_time:'2026-11-04 09:49:59'},{quote_time:'2026-11-04 10:02:00'},{quote_time:'2026-11-04 08:59:59'}]){
  const bad=structuredClone(feed);bad.market.partial_live.quotes=[{...quote,...change}];assert.equal(ctx.api.rows(bad,now).length,0,JSON.stringify(change));
 }
 for(const change of [{live_valid:true},{no_new_picks:false},{session_status:'休市'},{partial_live:{complete:true,quotes:[quote]}}]){
  assert.equal(ctx.api.rows({...feed,market:{...feed.market,...change}},now).length,0);
 }
 assert.equal(ctx.api.rows(feed,new Date('2026-11-04T08:59:59+08:00')).length,0);
 assert.equal(ctx.api.rows(feed,new Date('2026-11-04T13:30:00+08:00')).length,0);
 const duplicate=structuredClone(feed);duplicate.market.partial_live.quotes=[quote,quote];assert.equal(ctx.api.rows(duplicate,now).length,1);
 ctx.system=feed;ctx.api.render(now);assert.equal(elements.partialQuotesPanel.hidden,false);assert.match(elements.partialQuotes.textContent,/6150/);assert.match(elements.partialQuotes.textContent,/<img/);assert.match(elements.partialQuotesNote.textContent,/暫停新選股/);
 ctx.api.render(new Date('2026-11-04T10:10:01+08:00'));assert.equal(elements.partialQuotesPanel.hidden,true);assert.equal(elements.partialQuotes.textContent,'');
 assert.equal(feed.market.live_valid,false,'rendering must never enable global signals');
}
console.log('PASS partial quotes: synchronized browser/Android UI, freshness, privacy, text-only output and expiry');
