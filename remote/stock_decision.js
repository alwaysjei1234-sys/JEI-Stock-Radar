'use strict';
// JEI stock decision-card calculations. Pure functions; never infer missing market data.
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.JEIStockDecision=api;
})(typeof globalThis!=='undefined'?globalThis:null,function(){
  const valid=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
  function analyze({price,support,resistance,asof,quoteDate,flowDate}={}){
    if(!valid(price))return {state:'missing_price',message:'缺少有效現價，停止產生交易判斷'};
    const hasSupport=valid(support),hasResistance=valid(resistance);
    const pct=x=>Math.round((x/price-1)*10000)/100;
    let state='unverified',message='缺少經驗證的支撐壓力，暫不判定突破';
    if(hasResistance&&price>resistance){
      state='broken_resistance';
      message='現價已突破原壓力；原壓力不得再標示為上方壓力';
    }else if(hasSupport&&price<support){
      state='below_support';message='現價跌破原支撐，留意風險';
    }else if(hasSupport&&hasResistance&&support<=price&&price<=resistance){
      state='in_range';message='價格位於已提供的支撐壓力區間';
    }
    return {state,message,price,support:hasSupport?support:null,
      resistance:hasResistance?resistance:null,
      supportDistancePct:hasSupport?pct(support):null,
      resistanceDistancePct:hasResistance?pct(resistance):null,
      resistanceLabel:hasResistance&&price>resistance?'已突破的原壓力':'參考壓力',
      asof:asof||null,quoteDate:quoteDate||null,flowDate:flowDate||null,
      flowFresh:!!(asof&&flowDate&&asof===flowDate),
      caution:'支撐壓力為參考區間，非進出場保證；法人資料應標示其公布日期'};
  }
  return {analyze};
});
