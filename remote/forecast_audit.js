// JEI analyst forecast tracking (independent research tool)
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.JEIForecastAudit=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function evaluate(forecast,closes,asOf){
  const valid=forecast&&typeof forecast.target==='number'&&forecast.target>0&&
    typeof forecast.date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(forecast.date);
  if(!valid)return {state:'invalid',hit:null};
  const months=Number.isInteger(forecast.months)&&forecast.months>0?forecast.months:12;
  const expiry=new Date(forecast.date+'T00:00:00Z');
  expiry.setUTCMonth(expiry.getUTCMonth()+months);
  const deadline=expiry.toISOString().slice(0,10);
  const validAsOf=typeof asOf==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(asOf)&&Number.isFinite(Date.parse(asOf+'T00:00:00Z'));
  if(!validAsOf||asOf<forecast.date)return {state:'invalid',hit:null,deadline};
  const rows=(Array.isArray(closes)?closes:[]).filter(x=>x&&typeof x.date==='string'&&x.date>forecast.date&&x.date<=deadline&&x.date<=asOf&&typeof x.close==='number'&&x.close>0).sort((a,b)=>a.date.localeCompare(b.date));
  if(rows.some(x=>x.close>=forecast.target))return {state:'hit',hit:true,deadline};
  if(asOf<deadline)return {state:'pending',hit:null,deadline};
  // An expired forecast without verified end-of-horizon pricing cannot be scored as a miss.
  const last=rows[rows.length-1];
  // Trading holidays/weekends: allow the latest verified close within seven calendar days before expiry.
  const gap=last?Math.round((Date.parse(deadline+'T00:00:00Z')-Date.parse(last.date+'T00:00:00Z'))/86400000):Infinity;
  if(!last||gap>7)return {state:'missing_price',hit:null,deadline};
  return {state:'miss',hit:false,deadline};
 }
 function summarize(items){
  const scored=items.filter(x=>x.state==='hit'||x.state==='miss');
  const hits=scored.filter(x=>x.hit===true).length;
  return {completed:scored.length,hits,hitRate:scored.length?hits/scored.length:null,pending:items.filter(x=>x.state==='pending').length};
 }
 return {evaluate,summarize};
});
