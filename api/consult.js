// JEI Free Multi-AI consultation gateway.
// Zero-paid design: this endpoint NEVER falls back to Vercel AI Gateway.
// Free provider keys can be supplied per request from the user's device or
// configured as Vercel environment variables. No provider key is committed.

const PROVIDERS = {
  gemini_free: {
    label: "Gemini Free",
    key: "gemini",
    model: process.env.GEMINI_FREE_MODEL || "gemini-2.5-flash",
    via: "Google AI Studio Free Tier"
  },
  groq_oss: {
    label: "GPT-OSS 120B",
    key: "groq",
    model: process.env.GROQ_OSS_MODEL || "openai/gpt-oss-120b",
    via: "Groq Free Plan"
  },
  groq_qwen: {
    label: "Qwen 3.8 27B",
    key: "groq",
    model: process.env.GROQ_QWEN_MODEL || "qwen/qwen3.8-27b",
    via: "Groq Free Plan"
  },
  openrouter_free: {
    label: "OpenRouter Free",
    key: "openrouter",
    model: process.env.OPENROUTER_FREE_MODEL || "openrouter/free",
    via: "OpenRouter Free"
  },
  ollama_cloud: {
    label: "Ollama Cloud（試用額度）",
    key: "ollama",
    model: process.env.OLLAMA_CLOUD_MODEL || "gemma4:31b",
    via: "Ollama Cloud（會消耗 Ollama 額度）",
    opt_in: true
  }
};

function envKey(kind){
  if(kind==="gemini") return process.env.GEMINI_API_KEY || "";
  if(kind==="groq") return process.env.GROQ_API_KEY || "";
  if(kind==="openrouter") return process.env.OPENROUTER_API_KEY || "";
  if(kind==="ollama") return process.env.OLLAMA_API_KEY || "";
  return "";
}
function requestKey(body,kind){
  const k=body?.free_keys?.[kind];
  return String(k||"").trim() || envKey(kind);
}
function providerStatus(provider,body={}){
  const p=PROVIDERS[provider];
  if(!p) return {available:false};
  const fromEnv=!!envKey(p.key);
  const fromRequest=p.key==="ollama"?false:!!String(body?.free_keys?.[p.key]||"").trim();
  return {
    available:fromEnv||fromRequest,
    label:p.label,
    via:p.via,
    model:p.model,
    key_group:p.key,
    server_key:fromEnv,
    requires_client_key:!fromEnv
  };
}

function json(res,status,obj){
  res.statusCode=status;
  res.setHeader("Content-Type","application/json; charset=utf-8");
  res.setHeader("Cache-Control","no-store");
  res.setHeader("Access-Control-Allow-Origin","*");
  res.setHeader("Access-Control-Allow-Headers","Content-Type, X-JEI-Token");
  res.end(JSON.stringify(obj));
}
function textOf(v,max=15000){
  const s=typeof v==="string"?v:JSON.stringify(v??{});
  return s.length>max?s.slice(0,max)+"…":s;
}
function extractGemini(j){
  const p=j?.candidates?.[0]?.content?.parts||[];
  return p.map(x=>x?.text||"").join("\n").trim();
}
function extractChat(j){
  const c=j?.choices?.[0]?.message?.content;
  if(typeof c==="string") return c.trim();
  if(Array.isArray(c)) return c.map(x=>x?.text||x?.content||"").join("\n").trim();
  return "";
}
function friendlyError(e){
  const s=String(e?.message||e||"連線失敗");
  if(/429|rate limit|quota|resource exhausted|too many requests/i.test(s)) return "免費額度或速率限制已到，稍後再試";
  if(/401|403|api key|unauthorized|forbidden|invalid key/i.test(s)) return "免費 API Key 無效或尚未啟用";
  return s.slice(0,500);
}
async function fetchJson(url,opts,timeout=28000){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),timeout);
  try{
    const r=await fetch(url,{...opts,signal:ctrl.signal});
    const raw=await r.text();
    let j={}; try{j=JSON.parse(raw)}catch{}
    if(!r.ok){
      const msg=j?.error?.message||j?.message||raw||("HTTP "+r.status);
      throw new Error("HTTP "+r.status+" "+String(msg).slice(0,700));
    }
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
6. 回答繁體中文，先講結論，再講理由、風險與下一步；通常控制在 450 字內。
7. 多 AI 會診時要獨立判斷，不迎合其他模型。若不確定，明確寫出不確定因素。`;

function userPrompt(body){
  const history=(Array.isArray(body.history)?body.history:[]).slice(-8).filter(x=>x && typeof x==="object").map(x=>`${x.role==="assistant"?"assistant":"user"}: ${textOf(x.content,1000)}`).join("\n");
  return `使用者問題：${textOf(body.question,2800)}

JEI 市場/持股資料：
${textOf(body.context,14500)}

最近對話：
${history||"無"}

請根據上述資料做判斷。若問題需要未提供的即時新聞或行情，請直接說目前資料不足，不要自行編造。`;
}

async function askGemini(body,timeout=28000){
  const key=requestKey(body,"gemini");
  if(!key) return null;
  const model=PROVIDERS.gemini_free.model;
  const j=await fetchJson(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,{
    method:"POST",
    headers:{"x-goog-api-key":key,"Content-Type":"application/json"},
    body:JSON.stringify({
      system_instruction:{parts:[{text:SYSTEM}]},
      contents:[{role:"user",parts:[{text:userPrompt(body)}]}],
      generationConfig:{temperature:0.25,maxOutputTokens:900}
    })
  },timeout);
  return extractGemini(j)||"無有效回覆";
}
async function askGroq(body,provider,timeout=28000){
  const key=requestKey(body,"groq");
  if(!key) return null;
  const model=PROVIDERS[provider].model;
  const j=await fetchJson("https://api.groq.com/openai/v1/chat/completions",{
    method:"POST",
    headers:{"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    body:JSON.stringify({
      model,temperature:0.25,max_tokens:900,
      messages:[{role:"system",content:SYSTEM},{role:"user",content:userPrompt(body)}]
    })
  },timeout);
  return extractChat(j)||"無有效回覆";
}
async function askOpenRouter(body,timeout=28000){
  const key=requestKey(body,"openrouter");
  if(!key) return null;
  const j=await fetchJson("https://openrouter.ai/api/v1/chat/completions",{
    method:"POST",
    headers:{
      "Authorization":"Bearer "+key,
      "Content-Type":"application/json",
      "HTTP-Referer":"https://jei-stock-radar.vercel.app",
      "X-Title":"JEI Stock Radar"
    },
    body:JSON.stringify({
      model:PROVIDERS.openrouter_free.model,
      temperature:0.25,max_tokens:900,
      messages:[{role:"system",content:SYSTEM},{role:"user",content:userPrompt(body)}]
    })
  },timeout);
  return extractChat(j)||"無有效回覆";
}


async function askOllamaCloud(body,timeout=28000){
  // Only a server-owned API key is accepted; never forward a browser-supplied key.
  const key=envKey("ollama");
  if(!key) return null;
  const j=await fetchJson("https://ollama.com/api/chat",{
    method:"POST",
    headers:{"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    body:JSON.stringify({
      model:PROVIDERS.ollama_cloud.model,
      stream:false,
      messages:[{role:"system",content:SYSTEM},{role:"user",content:userPrompt(body)}],
      options:{temperature:0.25,num_predict:900}
    })
  },timeout);
  return String(j?.message?.content||"").trim()||"無有效回覆";
}

const CALLERS = {
  gemini_free: (body,timeout)=>askGemini(body,timeout),
  groq_oss: (body,timeout)=>askGroq(body,"groq_oss",timeout),
  groq_qwen: (body,timeout)=>askGroq(body,"groq_qwen",timeout),
  openrouter_free: (body,timeout)=>askOpenRouter(body,timeout),
  ollama_cloud: (body,timeout)=>askOllamaCloud(body,timeout)
};

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
  // Vercel functions have a 60s hard limit. Never loop through more models
  // sequentially for synthesis after the parallel independent opinions.
  const order=["gemini_free","groq_oss","groq_qwen","openrouter_free"];
  const chosen=order.find(p=>providerStatus(p,body).available);
  if(chosen){
    try{
      const out=await CALLERS[chosen](synthBody,12000);
      if(out) return out;
    }catch(e){}
  }
  return "免費 AI 已提供各自的獨立回覆，但綜合模型未在時限內完成。請直接比較以上各家結論、分歧與風險，不會重試付費模型。";
}

module.exports=async function handler(req,res){
  if(req.method==="OPTIONS"){
    res.statusCode=204;
    res.setHeader("Access-Control-Allow-Origin","*");
    res.setHeader("Access-Control-Allow-Headers","Content-Type, X-JEI-Token");
    res.end(); return;
  }

  if(req.method==="GET"){
    const providers={};
    for(const p of Object.keys(PROVIDERS)) providers[p]=providerStatus(p,{});
    return json(res,200,{
      ok:true,
      service:"JEI Free Multi-AI",
      free_only:true,
      paid_gateway:false,
      tokenRequired:!!process.env.JEI_CLIENT_TOKEN,
      providers
    });
  }
  if(req.method!=="POST") return json(res,405,{error:"Method not allowed"});

  const expected=process.env.JEI_CLIENT_TOKEN||"";
  const got=String(req.headers["x-jei-token"]||"");
  if(!expected) return json(res,503,{error:"JEI 中繼層尚未設定私人連線碼"});
  if(got!==expected) return json(res,401,{error:"JEI 私人連線碼不正確"});

  let body=req.body;
  if(typeof body==="string"){
    try{body=JSON.parse(body)}catch{return json(res,400,{error:"Invalid JSON"})}
  }
  if(!body || typeof body!=="object" || Array.isArray(body)) return json(res,400,{error:"JSON object required"});
  // Verify the private token without invoking any AI provider or using model quota.
  if(body.action==="verify_token") return json(res,200,{ok:true,verified:true,free_only:true,paid_gateway:false});
  if(typeof body.question!=="string" || !body.question.trim() || body.question.length>2800)
    return json(res,400,{error:"question must be a nonempty string up to 2800 characters"});
  if(body.providers!==undefined && (!Array.isArray(body.providers) || body.providers.length>5 || body.providers.some(x=>typeof x!=="string")))
    return json(res,400,{error:"providers must be a list of up to five names"});

  // An Ollama key being configured must never opt the user in automatically.
  const requested=Array.isArray(body.providers)&&body.providers.length
    ?body.providers:Object.keys(PROVIDERS).filter(p=>!PROVIDERS[p].opt_in);
  const providers=[...new Set(requested.map(String))].filter(x=>CALLERS[x]).slice(0,5);

  const settled=await Promise.all(providers.map(async provider=>{
    const st=providerStatus(provider,body);
    if(!st.available) return {provider,label:PROVIDERS[provider].label,skipped:true,reason:"尚未設定免費 API Key",key_group:PROVIDERS[provider].key};
    try{
      const text=await CALLERS[provider](body);
      if(!text) return {provider,label:PROVIDERS[provider].label,skipped:true,reason:"尚未設定免費 API Key"};
      return {provider,label:PROVIDERS[provider].label,text,via:st.via,model:st.model};
    }catch(e){
      return {provider,label:PROVIDERS[provider].label,error:friendlyError(e),via:st.via,model:st.model};
    }
  }));

  const answers=settled.filter(x=>x.text);
  const skipped=settled.filter(x=>x.skipped);
  const failed=settled.filter(x=>x.error);
  const consensus=answers.length
    ? await synthesize(body,answers)
    : "目前沒有免費 AI 成功回覆。請確認至少設定一組免費 API Key；若 Key 正確，可能是今日免費額度或速率限制已到。";

  return json(res,200,{
    ok:answers.length>0,
    free_only:!settled.some(x=>x.provider==="ollama_cloud" && !!x.text),
    ollama_credit_usage:settled.some(x=>x.provider==="ollama_cloud" && (!!x.text || !!x.error)),
    answers,skipped,failed,consensus,
    as_of:new Date().toISOString()
  });
};
