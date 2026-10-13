const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');

const html=fs.readFileSync('remote/index.html','utf8');
const start=html.indexOf('function finishAiConsult(){');
const stop=html.indexOf('let chatHistory=[],chatLastCode=',start);
assert(start>=0&&stop>start,'AI error/recovery functions must be present');
const funcs=html.slice(start,stop);
const allMessages=[];
const button={disabled:true};
let nextWatchdog=null,cleared=false;
const ctx={
  AI_LABELS:{groq_oss:'Groq OSS'},
  JEINative:{consultAI(){throw Error('native bridge unavailable')}},
  chatSay(who,message){allMessages.push({who,message})},
  toast(){},
  aiSelectedProviders(){return ['groq_oss']},
  settingGet(key){return key==='ai_backend_url'?'https://example.test/api/consult':'test-token'},
  aiContext(){return {}},
  freeAiKeys(){return {}},
  nativeOk(){return true},
  $:key=>key==='chatSendBtn'?button:null,
  setTimeout(fn){nextWatchdog=fn;return 10},
  clearTimeout(id){assert.equal(id,10);cleared=true},
  AbortController
};
vm.createContext(ctx);
vm.runInContext(
 "let aiPending=false,aiWatchdog=null,aiAbort=null,aiHealthLoaded=false,aiProviderStatus={},aiMode='single';let chatHistory=[{who:'me',text:'hello'}];"+
 funcs+
 ";globalThis.api={fail:failAiConsult,done:renderAiConsultResult,send:sendAiConsult,pending:()=>aiPending}",
 ctx,{filename:'remote/index.html#ai'}
);
ctx.api.send('test question');
assert.equal(ctx.api.pending(),false,'native synchronous failure must reset pending');
assert.equal(button.disabled,false,'native synchronous failure must reenable send');
assert(cleared);
assert(allMessages.some(x=>x.message.includes('native bridge unavailable')));

cleared=false;button.disabled=true;vm.runInContext('aiPending=true;aiWatchdog=10;',ctx);
ctx.api.fail('HTTP 403 Vercel Authentication Required');
assert.equal(ctx.api.pending(),false);
assert.equal(button.disabled,false);
assert(allMessages.some(x=>x.message.includes('存取遭拒')));

cleared=false;button.disabled=true;vm.runInContext('aiPending=true;aiWatchdog=10;',ctx);
ctx.api.done('<html>Login required</html>');
assert.equal(ctx.api.pending(),false);
assert.equal(button.disabled,false);
assert(allMessages.some(x=>x.message.includes('回傳不是有效')));

ctx.JEINative.consultAI=()=>{};
ctx.api.send('test timeout');
assert.equal(ctx.api.pending(),true);
assert.equal(button.disabled,true);
assert.equal(typeof nextWatchdog,'function');
nextWatchdog();
assert.equal(ctx.api.pending(),false);
assert.equal(button.disabled,false);
const msgCount=allMessages.length;
ctx.api.fail('duplicate error');
assert.equal(allMessages.length,msgCount,'late error must not duplicate a reply');

console.log('PASS: native exceptions, 403 login, invalid JSON, timeout and late callback recovery');
