const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('remote/index.html','utf8');
const code=html.slice(html.indexOf('let systemFetchPending=false;'),html.indexOf('function checkUpdate(){'));
const offline=fs.readFileSync('app/src/main/assets/index.html','utf8');
assert.equal(offline.slice(offline.indexOf('let systemFetchPending=false;'),offline.indexOf('function checkUpdate(){')),code,'packaged Android fallback must use the same recovery logic');
const fixture={updated_at:'2026-11-03 16:31',data_date:'2026-11-03',market:{mode:'最近收盤',actionable:false},holdings:{private:'must be stripped'}};
const elements={};let calls=[],timers=new Map(),timerId=0,renderCount=0;
const ctx={AbortController,Date,Promise,JEI_PRIVATE_APP:false,nativeOk:()=>false,
 $:id=>elements[id]??=( {textContent:'',classList:{add(){}}} ),
 seedMarketFromSystem(){},renderSystem(){renderCount++},showFeedStatus(){},
 setTimeout(fn,ms){const id=++timerId;timers.set(id,{fn,ms});return id},clearTimeout(id){timers.delete(id)},
 fetch:async url=>{calls.push(url);return {ok:true,json:async()=>structuredClone(fixture)}}};
vm.createContext(ctx);
vm.runInContext('let system={sentinel:true};'+code+';globalThis.api={refresh:refreshSystem,pending:()=>systemFetchPending,current:()=>system};',ctx);
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
(async()=>{
 await ctx.api.refresh();
 assert.equal(calls.length,1);assert.match(calls[0],/^\/remote\/system.json\?ts=/);
 assert.equal(ctx.api.current().data_date,fixture.data_date);
 assert.equal(ctx.api.current().market.actionable,false,'fallback must never upgrade market trust');
 assert.deepEqual(Object.keys(ctx.api.current().holdings),[],'public feed strips holdings');
 assert.equal(timers.size,0);
 calls=[];
 ctx.fetch=async url=>{calls.push(url);if(url.startsWith('/'))throw Error('HTTP 503');return {ok:true,json:async()=>structuredClone(fixture)}};
 await ctx.api.refresh();assert.equal(calls.length,2);assert.match(calls[1],/^https:\/\/raw.githubusercontent.com\//);
 calls=[];
 ctx.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>url.startsWith('/')?{updated_at:'today'}:structuredClone(fixture)}};
 await ctx.api.refresh();assert.equal(calls.length,2,'invalid primary schema falls back before changing displayed data');
 calls=[];
 ctx.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>url.startsWith('/')?{...fixture,market:{}}:structuredClone(fixture)}};
 await ctx.api.refresh();assert.equal(calls.length,2,'empty market must trigger repository fallback');
 assert.equal(ctx.api.current().market.mode,fixture.market.mode);
 // A stalled primary must start backup before its 12-second timeout.
 calls=[];let slowPrimary;
 ctx.fetch=url=>{calls.push(url);return url.startsWith('/')?new Promise(resolve=>{slowPrimary=resolve}):Promise.resolve({ok:true,json:async()=>structuredClone(fixture)})};
 const hedged=ctx.api.refresh();await flush();
 assert.equal(calls.length,1,'healthy fast primary avoids extra backup traffic');
 const hedge=[...timers.values()].find(t=>t.ms===1500);
 assert.ok(hedge,'backup must have a bounded head start delay');
 hedge.fn();await hedged;
 assert.equal(calls.length,2);assert.equal(timers.size,0,'winner clears all request timers');
 const winner=ctx.api.current();
 slowPrimary({ok:true,json:async()=>({...fixture,data_date:'2000-01-01'})});await flush();
 assert.equal(ctx.api.current(),winner,'losing source cannot overwrite the winner');
 const retained=ctx.api.current();calls=[];
 let lateResolve;
 ctx.fetch=url=>{calls.push(url);if(url.startsWith('/'))return new Promise(resolve=>{lateResolve=resolve});throw Error('offline')};
 const request=ctx.api.refresh();await flush();
 await ctx.api.refresh();assert.equal(calls.length,1,'concurrent refresh must not start another request');
 assert.equal(ctx.api.pending(),true);
 [...timers.values()].find(t=>t.ms===12000).fn();await request;
 assert.equal(ctx.api.pending(),false,'timeout must release future refreshes');
 assert.equal(ctx.api.current(),retained,'failed sources preserve last loaded feed');
 assert.match(elements.sysStatus.textContent,/更新失敗/);assert.equal(timers.size,0);
 lateResolve({ok:true,json:async()=>({...fixture,data_date:'2000-01-01'})});await flush();
 assert.equal(ctx.api.current(),retained,'late timed-out response must not overwrite the displayed feed');
 // A response whose body never finishes must also time out, then recover through backup.
 calls=[];ctx.fetch=async url=>{calls.push(url);return {ok:true,json:()=>url.startsWith('/')?new Promise(()=>{}):Promise.resolve(structuredClone(fixture))}};
 const bodyRequest=ctx.api.refresh();await flush();[...timers.values()].find(t=>t.ms===12000).fn();await bodyRequest;
 assert.equal(calls.length,2);assert.equal(ctx.api.pending(),false);assert.equal(timers.size,0);
 ctx.fetch=async()=>({ok:true,json:async()=>structuredClone(fixture)});
 await ctx.api.refresh();assert.match(elements.sysStatus.textContent,/已取得/);assert.ok(renderCount>=4);
 console.log('PASS system feed primary, backup, schema, timeout, body stall, overlap, late response, retry and privacy recovery');
})().catch(e=>{console.error(e);process.exitCode=1});

// Close snapshots survive restarts, but never become today's trusted feed.
for(const source of [html,offline]){
 const cacheCode=source.slice(source.indexOf('const CLOSE_CACHE_KEY='),source.indexOf('async function fetchSystemSource'));
 const recentCode=source.slice(source.indexOf('function isRecentCloseObservation('),source.indexOf('function updateFeedFreshness('));
 const entries=new Map(), labels={};
 class FixedDate extends Date { constructor(...args){super(...(args.length?args:['2026-11-04T05:00:00+08:00']))} }
 const sandbox={Date:FixedDate,localStorage:{getItem:k=>entries.get(k)||null,setItem:(k,v)=>entries.set(k,v)},
  $:id=>labels[id]??={textContent:''},seedMarketFromSystem(){},renderSystem(){},showFeedStatus(){}};
 vm.createContext(sandbox);
 vm.runInContext('let system={};'+recentCode+cacheCode+';globalThis.testCache={save:saveCloseSnapshot,restore:restoreCloseSnapshot,current:()=>system,key:CLOSE_CACHE_KEY}',sandbox);
 const close={data_date:'2026-11-03',updated_at:'2026-11-03 23:55',market:{mode:'今日收盤',close_count:1967,stale:false,live_valid:true},risk:{score:40},holdings:{private:'secret'},api_key:'secret'};
 sandbox.testCache.save(close);
 const saved=JSON.parse(entries.get(sandbox.testCache.key));
 assert.equal(Object.hasOwn(saved,'holdings'),false);assert.equal(Object.hasOwn(saved,'api_key'),false);
 assert.equal(sandbox.testCache.restore(),true);
 assert.equal(sandbox.testCache.current().market.stale,true);
 assert.equal(sandbox.testCache.current().market.live_valid,false);
 assert.equal(sandbox.testCache.current().market.actionable,false);
 assert.equal(sandbox.testCache.current().updated_at,close.updated_at,'cache never rewrites original quote time');
 sandbox.testCache.save({...close,data_date:'2026-11-02',updated_at:'2026-11-02 16:00'});
 assert.equal(JSON.parse(entries.get(sandbox.testCache.key)).data_date,'2026-11-03','older close cannot replace newer snapshot');
 entries.set(sandbox.testCache.key,'{broken');assert.equal(sandbox.testCache.restore(),false);
 entries.set(sandbox.testCache.key,JSON.stringify({...close,data_date:'2026-10-01',updated_at:'2026-10-01 16:00'}));
 assert.equal(sandbox.testCache.restore(),false,'expired snapshots rejected');
 entries.clear();sandbox.testCache.save({...close,market:{...close.market,mode:'盤中即時'}});
 assert.equal(entries.size,0,'intraday feed must not overwrite official-close cache');
 sandbox.localStorage.getItem=()=>{throw Error('storage disabled')};
 assert.equal(sandbox.testCache.restore(),false);assert.doesNotThrow(()=>sandbox.testCache.save(close));
 let nativeStored='';
 sandbox.JEINative={loadCloseSnapshot:()=>nativeStored,saveCloseSnapshot:raw=>{nativeStored=raw}};
 sandbox.testCache.save(close);
 assert.equal(JSON.parse(nativeStored).data_date,'2026-11-03','native cache works even when localStorage is disabled');
 assert.equal(sandbox.testCache.restore(),true,'packaged and remote UI share native persistence');
 assert.equal(Object.hasOwn(JSON.parse(nativeStored),'holdings'),false);

}
console.log('PASS browser and packaged close snapshots: persistence, read-only replay, privacy whitelist, rollback, invalid/expired/live rejection and blocked storage');
