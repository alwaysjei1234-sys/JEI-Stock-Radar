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
    if(hasSupport&&hasResistance&&support>=resistance)return {state:'invalid_levels',message:'支撐價必須低於壓力價，請檢查資料來源',price,support,resistance,flowVerified:false};
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
      flowVerified:false, // matching dates alone never verify institutional data
      caution:'支撐壓力為參考區間，非進出場保證；法人資料應標示其公布日期'};
  }
  function validateCloseFeed(feed,archive,code,today){
    const day=feed&&feed.data_date,market=feed&&feed.market;
    if(!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(day||'')||!today||day>today)return {ok:false,reason:'invalid_date'};
    if(!/^[0-9]{4}$/.test(code||''))return {ok:false,reason:'invalid_code'};
    if(!market||market.mode!=='今日收盤'||market.stale!==false||!Number.isFinite(market.close_count)||market.close_count<500)return {ok:false,reason:'unverified_market'};
    if(feed.source_data_date&&feed.source_data_date!==day)return {ok:false,reason:'source_date_mismatch'};
    if(!archive||archive.kind!=='official_daily_close'||!archive.days||!archive.days[day])return {ok:false,reason:'archive_missing'};
    const price=archive.days[day][code];
    if(!valid(price))return {ok:false,reason:'price_missing'};
    return {ok:true,price,date:day,isToday:day===today};
  }
  return {analyze,validateCloseFeed};
});
