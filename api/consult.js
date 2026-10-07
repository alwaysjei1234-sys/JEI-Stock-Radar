// JEI Multi-AI consultation gateway.
// Vercel Serverless Function. Provider API keys stay server-side.
// When provider keys are absent, Vercel AI Gateway is used through the
// deployment OIDC token, so JEI can run ChatGPT/Gemini/Claude/Grok without
// embedding any provider key in the Android app or public web UI.

const LABELS = {openai:"ChatGPT",gemini:"Gemini",anthropic:"Claude",xai:"Grok"};

const DIRECT_MODELS = {
  openai: process.env.OPENAI_MODEL || "gpt-5.6-luna",
  gemini: process.env.GEMINI_MODEL || "gemini-3.6-flash",
  anthropic: process.env.ANTHROPIC_MODEL || "claude-sonnet-4-5",
  xai: process.env.XAI_MODEL || "grok-4.5"
};

const GATEWAY_MODELS = {
  openai: process.env.JEI_OPENAI_GATEWAY_MODEL || "openai/gpt-5.6-sol",
  gemini: process.env.JEI_GEMINI_GATEWAY_MODEL || "google/gemini-3.1-pro-preview",
  anthropic: process.env.JEI_ANTHROPIC_GATEWAY_MODEL || "anthropic/claude-fable-5",
  xai: process.env.JEI_XAI_GATEWAY_MODEL || "xai/grok-4.5"
};

let oidcTokenPromise=null;
async function gatewayToken(){
  const direct=process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || "";
  if(direct) return direct;
  if(!oidcTokenPromise){
    oidcTokenPromise=(async()=>{
      try{
        const mod=await import("@vercel/oidc");
        return (await mod.getVercelOidcToken()) || "";
      }catch(e){
        return "";
      }
    })();
  }
  return oidcTokenPromise;
}

function providerKey(provider){
  if(provider==="openai") return process.env.OPENAI_API_KEY || "";
  if(provider==="gemini") return process.env.GEMINI_API_KEY || "";
  if(provider==="anthropic") return process.env.ANTHROPIC_API_KEY || "";
  if(provider==="xai") return process.env.XAI_API_KEY || "";
  return "";
}

async function providerStatus(provider){
  if(providerKey(provider)) return {available:true,via:"direct",model:DIRECT_MODELS[provider]};
  if(await gatewayToken()) return {available:true,via:"vercel-ai-gateway",model:GATEWAY_MODELS[provider]};
  return {available:false,via:"none",model:GATEWAY_MODELS[provider]};
}

function json(res,status,obj){
  res.statusCode=status;
  res.setHeader("Content-Type","application/json; charset=utf-8");
  res.setHeader("Cache-Control","no-store");
  res.setHeader("Access-Control-Allow-Origin","*");
  res.setHeader("Access-Control-Allow-Headers","Content-Type, X-JEI-Token");
  res.end(JSON.stringify(obj));
}

function textOf(v,max=18000){
  const s=typeof v==="string"?v:JSON.stringify(v??{});
  return s.length>max?s.slice(0,max)+"…":s;
}

function extractOpenAI(j){
  if(typeof j.output_text==="string"&&j.output_text.trim()) return j.output_text.trim();
  const out=[];
  for(const item of (j.output||[])){
    for(const c of (item.content||[])){
      if(typeof c.text==="string") out.push(c.text);
      else if(typeof c.output_text==="string") out.push(c.output_text);
    }
  }
  return out.join("\n").trim();
}

function extractGemini(j){
  const p=j?.candidates?.[0]?.content?.parts||[];
  return p.map(x=>x.text||"").join("\n").trim();
}

function extractAnthropic(j){
  return (j?.content||[]).map(x=>x?.text||"").join("\n").trim();
}

function extractChat(j){
  const c=j?.choices?.[0]?.message?.content;
  if(typeof c==="string") return c.trim();
  if(Array.isArray(c)) return c.map(x=>x?.text||x?.content||"").join("\n").trim();
  return "";
}

async function fetchJson(url,opts,timeout=50000){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),timeout);
  try{
    const r=await fetch(url,{...opts,signal:ctrl.signal});
    const raw=await r.text();
    let j={}; try{j=JSON.parse(raw)}catch{}
    if(!r.ok) throw new Error((j?.error?.message||j?.message||raw||("HTTP "+r.status)).slice(0,700));
    return j;
  }finally{clearTimeout(timer)}
}

const SYSTEM = `你是 JEI 台股投資分析會診成員。你會收到 JEI 的台股市場、族群、法人、候選榜與使用者持股資料。
規則：
1. 只能把提供的資料當成已知事實；不得假裝看過未提供的即時行情、新聞或網路。
2. 先確認資料時間與 stale 狀態。若資料過期或盤中覆蓋不足，先提醒，不能把舊價當現價。
3. 個股回答優先依序分析：大盤風險 → 族群強弱 → 價格/量能 → 法人資金 → 使用者成本與部位。
4. 不保證漲停、翻倍或獲利。可以給機率式判斷，但要說明關鍵條件與失效點。
5. 對持股要給可執行方案：續抱/觀察/減碼/停利，以及防守價或失效條件（若資料中有）。
6. 回答繁體中文，先講結論，再講理由、風險與下一步；通常控制在 500 字內。
7. 多 AI 會診時要獨立判斷，不迎合其他模型。若不確定，明確寫出不確定因素。`;

function userPrompt(body){
  const history=(body.history||[]).slice(-10).map(x=>`${x.role}: ${textOf(x.content,1400)}`).join("\n");
  return `使用者問題：${textOf(body.question,3500)}

JEI 市場/持股資料：
${textOf(body.context,18000)}

最近對話：
${history||"無"}

請根據上述資料做判斷。若問題需要未提供的即時新聞或行情，請直接說目前資料不足，不要自行編造。`;
}

async function askGateway(provider,body){
  const token=await gatewayToken();
  if(!token) return null;
  const model=GATEWAY_MODELS[provider];
  const payload={
    model,
    messages:[
      {role:"system",content:SYSTEM},
      {role:"user",content:userPrompt(body)}
    ],
    stream:false,
    max_tokens:1000
  };
  if(provider==="openai") payload.reasoning={effort:process.env.OPENAI_REASONING||"low"};
  const j=await fetchJson("https://ai-gateway.vercel.sh/v1/chat/completions",{
    method:"POST",
    headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  },52000);
  const out=extractChat(j);
  return out||"無有效回覆";
}

async function askOpenAI(body){
  const key=process.env.OPENAI_API_KEY;
  if(!key) return askGateway("openai",body);
  const j=await fetchJson("https://api.openai.com/v1/responses",{
    method:"POST",
    headers:{"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    body:JSON.stringify({
      model:DIRECT_MODELS.openai,
      reasoning:{effort:process.env.OPENAI_REASONING||"low"},
      max_output_tokens:1000,
      input:[
        {role:"system",content:[{type:"input_text",text:SYSTEM}]},
        {role:"user",content:[{type:"input_text",text:userPrompt(body)}]}
      ]
    })
  },52000);
  return extractOpenAI(j)||"無有效回覆";
}

async function askGemini(body){
  const key=process.env.GEMINI_API_KEY;
  if(!key) return askGateway("gemini",body);
  const j=await fetchJson(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(DIRECT_MODELS.gemini)}:generateContent`,{
    method:"POST",
    headers:{"x-goog-api-key":key,"Content-Type":"application/json"},
    body:JSON.stringify({
      system_instruction:{parts:[{text:SYSTEM}]},
      contents:[{role:"user",parts:[{text:userPrompt(body)}]}],
      generationConfig:{temperature:0.3,maxOutputTokens:1000}
    })
  },52000);
  return extractGemini(j)||"無有效回覆";
}

async function askAnthropic(body){
  const key=process.env.ANTHROPIC_API_KEY;
  if(!key) return askGateway("anthropic",body);
  const j=await fetchJson("https://api.anthropic.com/v1/messages",{
    method:"POST",
    headers:{"x-api-key":key,"anthropic-version":"2023-06-01","Content-Type":"application/json"},
    body:JSON.stringify({
      model:DIRECT_MODELS.anthropic,max_tokens:1000,temperature:0.3,system:SYSTEM,
      messages:[{role:"user",content:userPrompt(body)}]
    })
  },52000);
  return extractAnthropic(j)||"無有效回覆";
}

async function askXai(body){
  const key=process.env.XAI_API_KEY;
  if(!key) return askGateway("xai",body);
  const j=await fetchJson("https://api.x.ai/v1/chat/completions",{
    method:"POST",
    headers:{"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    body:JSON.stringify({
      model:DIRECT_MODELS.xai,temperature:0.3,max_tokens:1000,
      messages:[{role:"system",content:SYSTEM},{role:"user",content:userPrompt(body)}]
    })
  },52000);
  return extractChat(j)||"無有效回覆";
}

const CALLERS={openai:askOpenAI,gemini:askGemini,anthropic:askAnthropic,xai:askXai};

async function synthesize(body,answers){
  if(answers.length===1) return answers[0].text;
  const compact=answers.map(x=>`【${x.label}】\n${x.text}`).join("\n\n");
  const synthBody={...body,question:`請整合以下 AI 對同一問題的意見，輸出四段：
1. 共識結論
2. 關鍵分歧
3. 最大風險/失效條件
4. JEI 最終行動建議
不可用多數決取代判斷，也不要新增未提供的市場事實。

${compact}`};
  const order=["openai","gemini","anthropic","xai"];
  for(const provider of order){
    if(!(await providerStatus(provider)).available) continue;
    try{
      const out=await CALLERS[provider](synthBody);
      if(out) return out;
    }catch(e){}
  }
  return "各 AI 已完成回覆；綜合判讀模型暫時不可用，請以各家共同風險與失效條件為優先。";
}

module.exports = async function handler(req,res){
  if(req.method==="OPTIONS"){
    res.statusCode=204;
    res.setHeader("Access-Control-Allow-Origin","*");
    res.setHeader("Access-Control-Allow-Headers","Content-Type, X-JEI-Token");
    res.end();
    return;
  }

  if(req.method==="GET"){
    const providers={};
    for(const p of Object.keys(LABELS)) providers[p]={label:LABELS[p],...(await providerStatus(p))};
    return json(res,200,{
      ok:true,
      service:"JEI Multi-AI Gateway",
      gateway:!!(await gatewayToken()),
      tokenRequired:!!process.env.JEI_CLIENT_TOKEN,
      providers
    });
  }

  if(req.method!=="POST") return json(res,405,{error:"Method not allowed"});

  const expected=process.env.JEI_CLIENT_TOKEN||"";
  const got=String(req.headers["x-jei-token"]||"");
  if(!expected) return json(res,503,{error:"JEI AI gateway 尚未設定存取碼，為避免公開消耗 AI 額度已停止雲端問答"});
  if(got!==expected) return json(res,401,{error:"JEI 存取碼不正確"});

  let body=req.body;
  if(typeof body==="string"){
    try{body=JSON.parse(body)}catch{return json(res,400,{error:"Invalid JSON"})}
  }
  body=body||{};
  if(!String(body.question||"").trim()) return json(res,400,{error:"question required"});

  const requested=Array.isArray(body.providers)&&body.providers.length?body.providers:["openai"];
  const providers=[...new Set(requested.map(String))].filter(x=>CALLERS[x]).slice(0,4);
  const settled=await Promise.all(providers.map(async provider=>{
    const status=await providerStatus(provider);
    if(!status.available) return {provider,label:LABELS[provider],skipped:true,reason:"此 AI 尚未連線"};
    try{
      const text=await CALLERS[provider](body);
      if(text===null) return {provider,label:LABELS[provider],skipped:true,reason:"此 AI 尚未連線"};
      return {provider,label:LABELS[provider],text,via:status.via,model:status.model};
    }catch(e){
      return {provider,label:LABELS[provider],error:String(e?.message||e).slice(0,700),via:status.via,model:status.model};
    }
  }));

  const answers=settled.filter(x=>x.text);
  const skipped=settled.filter(x=>x.skipped);
  const failed=settled.filter(x=>x.error);
  let consensus="";
  if(answers.length) consensus=await synthesize(body,answers);
  else consensus="目前選取的 AI 都沒有成功回覆。請查看模型連線狀態或稍後再試。";

  return json(res,200,{
    ok:answers.length>0,
    answers,skipped,failed,consensus,
    as_of:new Date().toISOString()
  });
};
