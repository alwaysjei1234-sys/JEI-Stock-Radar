/* JEI broker target consensus: original implementation from user-visible public UI concepts.
   Target prices are analyst opinions, not guaranteed future values. */
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.JEITargetConsensus=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function calc(input){
  const price=input&&input.price!==null&&input.price!==undefined&&input.price!==''?Number(input.price):NaN;
  const validPrice=Number.isFinite(price)&&price>0;
  const rows=(Array.isArray(input&&input.reports)?input.reports:[]).filter(r=>
   r&&typeof r.broker==='string'&&r.broker.trim()&&typeof r.date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&
   typeof r.target==='number'&&Number.isFinite(r.target)&&r.target>0);
  const now=input&&/^\d{4}-\d{2}-\d{2}$/.test(input.asOf||'')?Date.parse(input.asOf+'T00:00:00Z'):null;
  // Future-dated reports must never contribute to a historical consensus.
  const eligible=now===null?[]:rows.filter(r=>Date.parse(r.date+'T00:00:00Z')<=now);
  const sorted=eligible.slice().sort((a,b)=>a.target-b.target);
  const count=sorted.length;
  const mean=count?sorted.reduce((s,r)=>s+r.target,0)/count:null;
  const median=count?(count%2?sorted[(count-1)/2].target:(sorted[count/2-1].target+sorted[count/2].target)/2):null;
  const min=count?sorted[0].target:null,max=count?sorted[count-1].target:null;
  const upside=validPrice&&mean!==null?(mean/price-1)*100:null;
  const dispersion=mean!==null&&mean>0?(max-min)/mean*100:null;
  const dated=rows.map(r=>({...r,ageDays:now===null?null:Math.round((now-Date.parse(r.date+'T00:00:00Z'))/86400000)}));
  const stale=dated.filter(r=>r.ageDays!==null&&r.ageDays>90).length;
  const future=dated.filter(r=>r.ageDays!==null&&r.ageDays<0).length;
  return {price:validPrice?price:null,count,mean,median,min,max,upsidePct:upside,dispersionPct:dispersion,
   reports:dated,staleCount:stale,futureDatedCount:future,
   warnings:[...(!validPrice?['股價未驗證']:[]),...(now===null?['查詢日期無效，無法計算共識']:[]),...(count<3?['券商樣本少於三家']:[]),...(stale?['包含超過90日報告']:[]),...(future?['未來日期報告已排除計算']:[]),...(dispersion!==null&&dispersion>30?['券商目標價分歧較大']:[])]};
 }
 return Object.freeze({calc});
});
