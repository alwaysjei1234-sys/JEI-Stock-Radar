const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('remote/cash.html','utf8');
const script=source.slice(source.indexOf('const JEI_STATIC_PENDING='),source.indexOf('const twDay='));
function page(native,data){
 const ctx={window:{},setTimeout,clearTimeout,Date,fetch:async()=>({ok:true,json:async()=>data})};
 if(native)ctx.JEINative={fetchStaticJson:kind=>queueMicrotask(()=>ctx.window.JEI_STATIC.onData(kind,JSON.stringify(data)))};
 vm.runInNewContext(script+';globalThis.read=readJeiStatic;',ctx);return ctx;
}
(async()=>{
 let cases=0;
 for(const native of [true,false]){
  for(const [kind,data] of [['system',{}],['daily',{}],['performance',{}],['system',null]]){
   await assert.rejects(page(native,data).read(kind),/格式錯誤/);cases++;
  }
  for(const [kind,data] of [['system',{market:{}}],['daily',{days:{},kind:'official_daily_close'}],['performance',{schema:1,strategies:{},mode:'official_daily_close_paper_observation'}]]){
   const result=await page(native,data).read(kind);assert.equal(JSON.stringify(result),JSON.stringify(data));cases++;
  }
 }
 console.log(`PASS ${cases} browser/native static JSON validation cases`);
})().catch(e=>{console.error(e);process.exitCode=1});
