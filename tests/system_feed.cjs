const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('remote/index.html','utf8');
const code=html.slice(html.indexOf('let systemFetchPending=false;'),html.indexOf('function checkUpdate(){'));
const offline=fs.readFileSync('app/src/main/assets/index.html','utf8');
assert.equal(offline.slice(offline.indexOf('let systemFetchPending=false;'),offline.indexOf('function checkUpdate(){')),code,'packaged Android fallback must use the same recovery logic');
const fixture={updated_at:'2026-11-03 16:31',data_date:'2026-11-03',market:{actionable:false},holdings:{private:'must be stripped'}};
const elements={};let calls=[],timers=new Map(),timerId=0,renderCount=0;
const ctx={AbortController,Date,Promise,JEI_PRIVATE_APP:false,nativeOk:()=>false,
 $:id=>elements[id]??=( {textContent:'',classList:{add(){}}} ),
 seedMarketFromSystem(){},renderSystem(){renderCount++},showFeedStatus(){},
 setTimeout(fn){const id=++timerId;timers.set(id,fn);return id},clearTimeout(id){timers.delete(id)},
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
 const retained=ctx.api.current();calls=[];
 let lateResolve;
 ctx.fetch=url=>{calls.push(url);if(url.startsWith('/'))return new Promise(resolve=>{lateResolve=resolve});throw Error('offline')};
 const request=ctx.api.refresh();await flush();
 await ctx.api.refresh();assert.equal(calls.length,1,'concurrent refresh must not start another request');
 assert.equal(ctx.api.pending(),true);
 [...timers.values()][0]();await request;
 assert.equal(ctx.api.pending(),false,'timeout must release future refreshes');
 assert.equal(ctx.api.current(),retained,'failed sources preserve last loaded feed');
 assert.match(elements.sysStatus.textContent,/更新失敗/);assert.equal(timers.size,0);
 lateResolve({ok:true,json:async()=>({...fixture,data_date:'2000-01-01'})});await flush();
 assert.equal(ctx.api.current(),retained,'late timed-out response must not overwrite the displayed feed');
 // A response whose body never finishes must also time out, then recover through backup.
 calls=[];ctx.fetch=async url=>{calls.push(url);return {ok:true,json:()=>url.startsWith('/')?new Promise(()=>{}):Promise.resolve(structuredClone(fixture))}};
 const bodyRequest=ctx.api.refresh();await flush();[...timers.values()][0]();await bodyRequest;
 assert.equal(calls.length,2);assert.equal(ctx.api.pending(),false);assert.equal(timers.size,0);
 ctx.fetch=async()=>({ok:true,json:async()=>structuredClone(fixture)});
 await ctx.api.refresh();assert.match(elements.sysStatus.textContent,/已取得/);assert.ok(renderCount>=4);
 console.log('PASS system feed primary, backup, schema, timeout, body stall, overlap, late response, retry and privacy recovery');
})().catch(e=>{console.error(e);process.exitCode=1});
