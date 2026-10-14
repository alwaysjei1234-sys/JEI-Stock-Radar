const assert=require('node:assert/strict');
const apiPath='../api/consult.js';
process.env.JEI_CLIENT_TOKEN='test-secret-not-real';
process.env.GROQ_API_KEY='test-groq-key-not-real';
delete process.env.GEMINI_API_KEY;
delete process.env.OPENROUTER_API_KEY;
const handler=require(apiPath);
let externalCalls=0;

async function invoke(method,headers={},body=null){
  return new Promise((resolve,reject)=>{
    const res={
      statusCode:200,headers:{},
      setHeader(k,v){this.headers[k.toLowerCase()]=v},
      end(raw=''){let parsed;try{parsed=raw?JSON.parse(raw):null}catch(e){return reject(e)}
        resolve({code:this.statusCode,headers:this.headers,json:parsed})}
    };
    try{Promise.resolve(handler({method,headers,body},res)).catch(reject)}catch(e){reject(e)}
  });
}

async function main(){
  let r=await invoke('GET');
  assert.equal(r.code,200);
  assert.equal(r.json.free_only,true);
  assert.equal(r.json.paid_gateway,false);
  assert.equal(r.json.providers.groq_oss.server_key,true);
  assert(!JSON.stringify(r.json).includes('test-groq-key-not-real'),'must not leak server key');

  r=await invoke('POST',{'x-jei-token':'wrong'},{question:'test'});
  assert.equal(r.code,401);
  r=await invoke('POST',{'x-jei-token':'test-secret-not-real'},{question:''});
  assert.equal(r.code,400);
  assert.equal(externalCalls,0);
  // Token validation is free, private and must never reach AI providers.
  r=await invoke('POST',{'x-jei-token':'wrong'},{action:'verify_token'});
  assert.equal(r.code,401);
  r=await invoke('POST',{'x-jei-token':'test-secret-not-real'},{action:'verify_token'});
  assert.equal(r.code,200);
  assert.equal(r.json.verified,true);
  assert.equal(r.json.free_only,true);
  assert.equal(r.json.paid_gateway,false);
  assert.equal(externalCalls,0);
  assert(!JSON.stringify(r.json).includes('test-secret-not-real'),'never expose private token');

  global.fetch=async (url,options)=>{
    assert.match(url,/^https:\/\/api\.groq\.com\/openai\/v1\/chat\/completions$/);
    assert.equal(options.method,'POST');
    const post=JSON.parse(options.body);
    assert(post.model==='openai/gpt-oss-120b'||post.model==='qwen/qwen3.8-27b');
    externalCalls++;
    if(externalCalls===3)throw Error('synthesis temporarily unavailable');
    return {ok:true,status:200,text:async()=>JSON.stringify({
      choices:[{message:{content:post.model==='openai/gpt-oss-120b'?'觀點A':'觀點B'}}]
    })};
  };
  r=await invoke('POST',{'x-jei-token':'test-secret-not-real'},{
    question:'測試市場風險',context:{data_date:'2026-10-13'},
    providers:['groq_oss','groq_qwen'],history:[]
  });
  assert.equal(r.code,200);
  assert.equal(r.json.free_only,true);
  assert.equal(r.json.ok,true);
  assert.equal(r.json.answers.length,2);
  assert(r.json.consensus.includes('未在時限內完成'),'independent opinions retained after synthesis failure');
  assert.equal(externalCalls,3,'maximum one synthesis request, no sequential retry chain');
  assert(!JSON.stringify(r.json).includes('test-secret-not-real'));

  global.fetch=async()=>{throw Error('HTTP 429 rate limit')};
  r=await invoke('POST',{'x-jei-token':'test-secret-not-real'},{
    question:'驗證額度限制',providers:['groq_oss'],history:[]
  });
  assert.equal(r.code,200);
  assert.equal(r.json.ok,false);
  assert.equal(r.json.failed.length,1);
  assert.match(r.json.failed[0].error,/免費額度|速率限制/);
  console.log('PASS: free-only AI gateway health, auth, 2 providers, one synthesis and outage fallback');
}
main().catch(e=>{console.error(e);process.exitCode=1});
