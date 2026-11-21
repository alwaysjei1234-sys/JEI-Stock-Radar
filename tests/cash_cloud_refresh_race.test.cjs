const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('remote/cash.html','utf8');
const start=html.indexOf('async function loadCloudPerformance()');
const source=(html.match(/let CLOUD_PERFORMANCE_REQUEST=0;/)?.[0]||'')+html.slice(start,html.indexOf("$('cloudRefresh').onclick",start));
function harness(){
 const nodes=new Map(),pending=[];
 const node=()=>({textContent:'',children:[],replaceChildren(){this.children=[]},appendChild(x){this.children.push(x)}});
 const get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
 const context={$:get,document:{createElement:node},readJeiStatic:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),twDay:()=> '2026-11-20',money:String,renderStrategyComparison:d=>{get('cloudKpiDate').textContent=d.last_processed_day},renderCloudEvidence:()=>{}};
 vm.runInNewContext(source+';globalThis.run=loadCloudPerformance;',context);
 return {get,pending,run:context.run};
}
const feed=day=>({last_processed_day:day,capital_per_strategy:1000000,strategies:{}});
(async()=>{
 for(const late of ['success','error']){
  const h=harness(),old=h.run(),latest=h.run();h.pending[1].resolve(feed('2026-11-20'));await latest;
  if(late==='success')h.pending[0].resolve(feed('2026-11-19'));else h.pending[0].reject(Error('old request offline'));
  await old;
  assert.match(h.get('cloudStatus').textContent,/已更新交易日 2026-11-20/);
  assert.equal(h.get('cloudKpiDate').textContent,'2026-11-20');
  assert.equal(h.get('cloudRows').children.length,4);
 }
 const h=harness(),failed=h.run();h.pending[0].reject(Error('latest offline'));await failed;
 assert.match(h.get('cloudStatus').textContent,/latest offline/);
 const retry=h.run();h.pending[1].resolve(feed('2026-11-20'));await retry;
 assert.match(h.get('cloudStatus').textContent,/已更新交易日 2026-11-20/);
 console.log('PASS four cloud refresh race, latest failure and retry scenarios');
})().catch(e=>{console.error(e);process.exitCode=1});
