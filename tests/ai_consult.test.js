const assert=require("node:assert/strict");
const test=require("node:test");
const handler=require("../api/consult.js");

function invoke(body,method="POST",token="test-token"){
  return new Promise(resolve=>{
    const headers={};
    const res={statusCode:200,setHeader(k,v){headers[k]=v;},
      end(text){resolve({status:this.statusCode,body:text?JSON.parse(text):null,headers});}};
    handler({method,headers:{"x-jei-token":token},body},res).catch(e=>resolve({error:String(e)}));
  });
}

test("AI consultation rejects malformed request without calling providers",async()=>{
  const old=process.env.JEI_CLIENT_TOKEN;
  process.env.JEI_CLIENT_TOKEN="test-token";
  try{
    for(const body of [[],null,{question:""},{question:123},{question:"x".repeat(2801)},
                       {question:"test",providers:"groq_oss"},
                       {question:"test",providers:[1]}]){
      const result=await invoke(body);
      assert.equal(result.status,400,JSON.stringify(body).slice(0,80));
    }
    const verified=await invoke({action:"verify_token"});
    assert.equal(verified.status,200);
    assert.equal(verified.body.verified,true);
  }finally{
    if(old===undefined)delete process.env.JEI_CLIENT_TOKEN;
    else process.env.JEI_CLIENT_TOKEN=old;
  }
});


test("AI provider discovery exposes all five choices without secrets",async()=>{
  const response=await invoke(null,"GET");
  assert.equal(response.status,200);
  assert.equal(response.body.free_only,true);
  assert.equal(response.body.paid_gateway,false);
  assert.deepEqual(Object.keys(response.body.providers).sort(),
    ["gemini_free","groq_oss","groq_qwen","openrouter_free","ollama_cloud"].sort());
  for(const provider of Object.values(response.body.providers)){
    assert.equal(typeof provider.available,"boolean");
    assert.equal(typeof provider.label,"string");
    assert.equal(typeof provider.server_key,"boolean");
    assert.equal(typeof provider.requires_client_key,"boolean");
  }
});

test("AI consultation returns explicit skipped status for five unconfigured models",async()=>{
  const keys=["JEI_CLIENT_TOKEN","GEMINI_API_KEY","GROQ_API_KEY","OPENROUTER_API_KEY","OLLAMA_API_KEY"];
  const saved=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try{
    process.env.JEI_CLIENT_TOKEN="test-token";
    for(const key of keys.slice(1))delete process.env[key];
    const response=await invoke({question:"市場風險？",providers:["gemini_free","groq_oss","groq_qwen","openrouter_free","ollama_cloud"]});
    assert.equal(response.status,200);
    assert.equal(response.body.ok,false);
    assert.equal(response.body.answers.length,0);
    assert.equal(response.body.skipped.length,5);
    assert.equal(response.body.failed.length,0);
  }finally{
    for(const key of keys){
      if(saved[key]===undefined)delete process.env[key];
      else process.env[key]=saved[key];
    }
  }
});
