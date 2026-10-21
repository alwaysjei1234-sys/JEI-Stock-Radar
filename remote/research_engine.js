/* JEI research decision engine v1: pure functions, no external dependencies.
   Inputs are verified records; absent numbers must stay unknown. */
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.JEIResearch=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const num=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
 const validDate=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
 function classifyEvidence(items){
  const allowed=new Set(['confirmed','inference','rumor']);
  return (Array.isArray(items)?items:[]).map(item=>({
   text:String(item&&item.text||''),
   status:allowed.has(item&&item.status)?item.status:'unverified',
   source:item&&item.source?String(item.source):null,
   date:item&&validDate(item.date)?item.date:null
  }));
 }
 function research(stock){
  const fields=['revenueYoY','epsTTM','grossMargin','operatingMargin','freeCashFlow','debtRatio'];
  const metrics={};let verified=0;
  fields.forEach(key=>{const v=num(stock&&stock[key]);metrics[key]=v;if(v!==null)verified++});
  const evidence=classifyEvidence(stock&&stock.evidence);
  const confirmed=evidence.filter(e=>e.status==='confirmed'&&e.source&&e.date).length;
  const peers=Array.isArray(stock&&stock.peers)?stock.peers.filter(p=>p&&p.symbol&&num(p.revenueYoY)!==null&&num(p.operatingMargin)!==null):[];
  return {symbol:String(stock&&stock.symbol||''),metrics,coverage:{verified,total:fields.length,ratio:verified/fields.length},
   evidence,confirmedEvidence:confirmed,peerComparisonReady:peers.length>=2,
   warnings:[...(verified<fields.length?['基本面資料不完整']:[]),...(confirmed===0?['缺少附來源及日期的確認事實']:[]),...(peers.length<2?['同業可比較樣本不足兩家']:[])]};
 }
 function scenario(input){
  const price=num(input&&input.price),support=num(input&&input.support),resistance=num(input&&input.resistance);
  if(price===null||support===null||resistance===null||support<=0||resistance<=support)
   return {state:'insufficient',action:'資料不足，不產生交易訊號',invalidates:null};
  if(price<support)return {state:'breakdown',action:'跌破支撐：停止加碼，重新評估風險',invalidates:'重新站回支撐並確認'};
  if(price>resistance)return {state:'strength',action:'突破壓力：觀察量價與是否站穩，不保證續漲',invalidates:'跌回壓力位下方'};
  return {state:'range',action:'區間震盪：等待有效突破或跌破',invalidates:'突破壓力或跌破支撐'};
 }
 function performance(events,quotes,days){
  const horizons=Array.isArray(days)?days:[3,7,15,30,60,90];
  const result=[];
  for(const e of (Array.isArray(events)?events:[])){
   const entry=num(e&&e.entryPrice),symbol=String(e&&e.symbol||'');
   const series=Array.isArray(quotes&&quotes[symbol])?quotes[symbol].filter(x=>validDate(x.date)&&num(x.close)!==null).slice().sort((a,b)=>a.date.localeCompare(b.date)):[];
   const after=series.filter(x=>validDate(e&&e.date)&&x.date>e.date);
   for(const d of horizons){
    if(!Number.isInteger(d)||d<1)continue;
    const q=after[d-1];
    const state=entry===null||entry<=0||!validDate(e.date)?'invalid_entry':q?'completed':'pending';
    const gross=state==='completed'?(q.close/entry-1)*100:null;
    const fee=num(e&&e.roundTripCostPct);
    result.push({id:String(e&&e.id||''),symbol,days:d,state,exitDate:q?q.date:null,
      grossPct:gross,netPct:gross!==null&&fee!==null?gross-fee:null});
   }
  }
  return result;
 }
 return Object.freeze({research,scenario,performance,classifyEvidence});
});
