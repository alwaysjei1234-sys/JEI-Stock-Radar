const assert=require('node:assert/strict');
process.env.JEI_CLIENT_TOKEN='test-local-token';
process.env.OLLAMA_API_KEY='test-ollama-secret';
process.env.OLLAMA_CLOUD_MODEL='gemma4:31b';
delete process.env.GEMINI_API_KEY;
delete process.env.GROQ_API_KEY;
delete process.env.OPENROUTER_API_KEY;
const handler=require('../api/consult.js');
let calls=0;
async function invoke(method,headers={},body=null){
  return new Promise((resolve,reject)=>{
    const res={statusCode:200,headers:{},
      setHeader(k,v){this.headers[k.toLowerCase()]=v},
      end(raw=''){try{resolve({code:this.statusCode,json:raw?JSON.parse(raw):null})}catch(e){reject(e)}}
    };
    Promise.resolve(handler({method,headers,body},res)).catch(reject);
  });
}
async function main(){
  let r=await invoke('GET');
  assert.equal(r.json.providers.ollama_cloud.available,true);
  assert.equal(r.json.providers.ollama_cloud.server_key,true);
  assert.equal(r.json.providers.ollama_cloud.model,'gemma4:31b');
  assert(!JSON.stringify(r.json).includes('test-ollama-secret'));
  r=await invoke('POST',{'x-jei-token':'wrong'},{question:'test',providers:['ollama_cloud']});
  assert.equal(r.code,401);assert.equal(calls,0);
  global.fetch=async(url,options)=>{
    calls++;assert.equal(url,'https://ollama.com/api/chat');
    assert.equal(options.headers.Authorization,'Bearer test-ollama-secret');
    const request=JSON.parse(options.body);
    assert.equal(request.model,'gemma4:31b');
    assert.equal(request.stream,false);
    assert.match(request.messages[0].content,/過期|stale/);
    assert.match(request.messages[1].content,/台股/);
    return {ok:true,status:200,text:async()=>JSON.stringify({message:{role:'assistant',content:'資料不足，不能推測盤中行情。'}})};
  };
  // No explicit opt-in: Ollama must never be invoked even when key exists.
  r=await invoke('POST',{'x-jei-token':'test-local-token'},{question:'台股分析',context:{data_date:'2026-10-16'}});
  assert.equal(calls,0);
  assert.equal(r.json.ollama_credit_usage,false);
  assert.equal(r.json.free_only,true);
  r=await invoke('POST',{'x-jei-token':'test-local-token'},{question:'台股分析',providers:['ollama_cloud']});
  assert.equal(calls,1);
  assert.equal(r.json.ok,true);
  assert.equal(r.json.answers.length,1);
  assert.equal(r.json.answers[0].provider,'ollama_cloud');
  assert.match(r.json.consensus,/資料不足/);
  assert.equal(r.json.ollama_credit_usage,true);
  assert.equal(r.json.free_only,false);
  assert(!JSON.stringify(r.json).includes('test-ollama-secret'));
  // Ignore browser-supplied fake Ollama API keys. Only Vercel env is allowed.
  delete process.env.OLLAMA_API_KEY;
  r=await invoke('POST',{'x-jei-token':'test-local-token'},{
    question:'台股分析',providers:['ollama_cloud'],free_keys:{ollama:'browser-key-must-be-ignored'}
  });
  assert.equal(calls,1);
  assert.equal(r.json.ok,false);
  assert.equal(r.json.skipped.length,1);
  console.log('PASS: Ollama API contract, opt-in-only, token auth, no browser key, single reply');
}
main().catch(e=>{console.error(e);process.exitCode=1});
