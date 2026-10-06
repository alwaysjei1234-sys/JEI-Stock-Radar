// JEI Multi-AI consultation gateway.
// Deploy as a Vercel Serverless Function. Keep provider API keys in Vercel env vars.
const LABELS = {openai:"ChatGPT",gemini:"Gemini",anthropic:"Claude",xai:"Grok"};

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
function extractXai(j){
  return String(j?.choices?.[0]?.message?.content||"").trim();
}
async function fetchJson(url,opts,timeout=50000){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),timeout);
  try{
    const r=await fetch(url,{...opts,signal:ctrl.signal});
    const raw=await r.text();
    let j={}; try{j=JSON.parse(raw)}catch{}
    if(!r.ok) throw new Error((j?.error?.message||j?.message||raw||("HTTP "+r.status)).slice(0,500));
    return j;
  }finally{clearTimeout(timer)}
}

const SYSTEM = `你是 JEI 台股投資分析會診成員。只依照使用者問題與提供的 JEI 資料回答。
規則：
1. 不得把推測說成已發生事實，不得保證漲停或獲利。
2. 優先分析價格動能、成交量/成交值、族群、法人資金、持股成本與市場風險。
3. 資料時間戳若不是最新，必須提醒。
4. 回答繁體中文，先講結論，再講理由與風險；控制在 450 字內。
5. 若其他 AI 可能有不同觀點，明確說明關鍵不確定因素。`;

function userPrompt(body){
  const history=(body.history||[]).slice(-8).map(x=>`${x.role}: ${textOf(x.content,1200)}`).join("\n");
  return `使用者問題：${textOf(body.question,3000)}

JEI 市場/持股資料：
${textOf(body.context,15000)}

最近對話：
${history||"無"}

請做獨立判斷，不要假裝看過未提供的即時行情或網路資料。`;
}

async function askOpenAI(body){
  const key=process.env.OPENAI_API_KEY; if(!key) return null;
  const model=process.env.OPENAI_MODEL||"gpt-5.6-luna";
  const j=await fetchJson("https://api.openai.com/v1/responses",{
    method:"POST",
    headers:{"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    body:JSON.stringify({
      model,
      reasoning:{effort:process.env.OPENAI_REASONING||"low"},
      max_output_tokens:900,
      input:[
        {role:"system",content:[{type:"input_text",text:SYSTEM}]},
        {role:"user",content:[{type:"input_text",text:userPrompt(body)}]}
      ]
    })
  });
  return extractOpenAI(j)||"無有效回覆";
}
async function askGemini(body){
  const key=process.env.GEMINI_API_KEY; if(!key) return null;
  const model=process.env.GEMINI_MODEL||"gemini-3.6-flash";
  const j=await fetchJson(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,{
    method:"POST",
    headers:{"x-goog-api-key":key,"Content-Type":"application/json"},
    body:JSON.stringify({
      system_instruction:{parts:[{text:SYSTEM}]},
      contents:[{role:"user",parts:[{text:userPrompt(body)}]}],
      generationConfig:{temperature:0.35,maxOutputTokens:900}
    })
  });
  return extractGemini(j)||"無有效回覆";
}
async function askAnthropic(body){
  const key=process.env.ANTHROPIC_API_KEY; if(!key) return null;
  const model=process.env.ANTHROPIC_MODEL||"claude-sonnet-4-5";
  const j=await fetchJson("https://api.anthropic.com/v1/messages",{
    method:"POST",
    headers:{"x-api-key":key,"anthropic-version":"2023-06-01","Content-Type":"application/json"},
    body:JSON.stringify({
      model,max_tokens:900,temperature:0.35,system:SYSTEM,
      messages:[{role:"user",content:userPrompt(body)}]
    })
  });
  return extractAnthropic(j)||"無有效回覆";
}
async function askXai(body){
  const key=process.env.XAI_API_KEY; if(!key) return null;
  const model=process.env.XAI_MODEL||"grok-4.5";
  const j=await fetchJson("https://api.x.ai/v1/chat/completions",{
    method:"POST",
    headers:{"Authorization":"Bearer "+key,"Content-Type":"application/json"},
    body:JSON.stringify({
      model,temperature:0.35,max_tokens:900,
      messages:[{role:"system",content:SYSTEM},{role:"user",content:userPrompt(body)}]
    })
  });
  return extractXai(j)||"無有效回覆";
}
const CALLERS={openai:askOpenAI,gemini:askGemini,anthropic:askAnthropic,xai:askXai};

async function synthesize(body,answers){
  if(answers.length===1) return answers[0].text;
  const compact=answers.map(x=>`【${x.label}】\n${x.text}`).join("\n\n");
  const synthBody={...body,question:`請整合以下 AI 對同一問題的意見，輸出「共識結論、分歧點、最重要風險、JEI最終行動建議」。不可用多數決取代判斷，也不要新增未提供的市場事實。\n\n${compact}`};
  try{
    if(process.env.OPENAI_API_KEY) return await askOpenAI(synthBody);
    if(process.env.GEMINI_API_KEY) return await askGemini(synthBody);
    if(process.env.ANTHROPIC_API_KEY) return await askAnthropic(synthBody);
    if(process.env.XAI_API_KEY) return await askXai(synthBody);
  }catch(e){}
  return "各 AI 已完成回覆；目前未設定綜合判讀模型，請比較各家理由與風險。";
}

module.exports = async function handler(req,res){
  if(req.method==="OPTIONS"){res.statusCode=204;res.setHeader("Access-Control-Allow-Origin","*");res.setHeader("Access-Control-Allow-Headers","Content-Type, X-JEI-Token");res.end();return}
  if(req.method==="GET"){
    return json(res,200,{ok:true,service:"JEI Multi-AI Gateway",providers:{
      openai:!!process.env.OPENAI_API_KEY,gemini:!!process.env.GEMINI_API_KEY,
      anthropic:!!process.env.ANTHROPIC_API_KEY,xai:!!process.env.XAI_API_KEY
    }});
  }
  if(req.method!=="POST") return json(res,405,{error:"Method not allowed"});

  const expected=process.env.JEI_CLIENT_TOKEN||"";
  const got=String(req.headers["x-jei-token"]||"");
  if(expected && got!==expected) return json(res,401,{error:"JEI access token invalid"});

  let body=req.body;
  if(typeof body==="string"){try{body=JSON.parse(body)}catch{return json(res,400,{error:"Invalid JSON"})}}
  body=body||{};
  if(!String(body.question||"").trim()) return json(res,400,{error:"question required"});

  const requested=Array.isArray(body.providers)&&body.providers.length?body.providers:["openai","gemini","anthropic","xai"];
  const providers=[...new Set(requested.map(String))].filter(x=>CALLERS[x]).slice(0,4);
  const settled=await Promise.all(providers.map(async provider=>{
    try{
      const text=await CALLERS[provider](body);
      if(text===null) return {provider,label:LABELS[provider],skipped:true,reason:"API Key 尚未設定"};
      return {provider,label:LABELS[provider],text};
    }catch(e){
      return {provider,label:LABELS[provider],error:String(e?.message||e).slice(0,600)};
    }
  }));
  const answers=settled.filter(x=>x.text);
  const skipped=settled.filter(x=>x.skipped);
  const failed=settled.filter(x=>x.error);
  let consensus="";
  if(answers.length) consensus=await synthesize(body,answers);
  else consensus="目前選取的 AI 都尚未成功連線。請確認雲端 API Key、模型名稱與額度。";

  return json(res,200,{
    ok:answers.length>0,
    answers,skipped,failed,consensus,
    as_of:new Date().toISOString()
  });
};
