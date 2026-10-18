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
