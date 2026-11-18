/* JEI Strategy Integration: one provenance-aware advisory for UI, AI and paper.
 * This module NEVER places orders, edits prices, validates broker fills,
 * or treats short-horizon observed returns as independent OOS evidence.
 * Require explicit, bounded 10/10 weak samples for the strongest warning.
 */
(function(root, build){
  const api=build();
  if(typeof module==='object' && module.exports)module.exports=api;
  if(root)root.JEIStrategyIntegration=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const SOURCE='forward_official_close_pick_validation';
  const WEAK='ALL_OBSERVED_SHORT_HORIZONS_WEAK';
  function canonicalDay(value){
    if(typeof value!=='string'||!/^20\d\d-\d\d-\d\d$/.test(value))return null;
    const milliseconds=Date.parse(value+'T00:00:00Z');
    if(!Number.isFinite(milliseconds))return null;
    return new Date(milliseconds).toISOString().slice(0,10)===value?milliseconds:null;
  }
  function positiveInt(n){return Number.isInteger(n)&&n>=0?n:null;}
  function summarize(feed){
    const unknown={mode:'unverified',status:'UNVERIFIED',notice:'策略觀察績效尚未完成核對；目前沒有已驗證的可交易勝率。',shortNotice:'策略績效未驗證',sourceDay:null,
      advisory_only:true,independent_oos_verified:false,real_execution_verified:false,
      evaluated_windows:0,underperforming_windows:0};
    if(!feed||typeof feed!=='object'||Array.isArray(feed))return {...unknown};
    const h=feed.strategy_health;
    if(!h||typeof h!=='object'||Array.isArray(h)||h.source!==SOURCE)return {...unknown};
    const today=canonicalDay(feed.data_date),day=canonicalDay(h.latest_official_day);
    const checked=positiveInt(h.evaluated_windows),weak=positiveInt(h.underperforming_windows),required=positiveInt(h.required_windows);
    if(today===null||day===null||day>today||today-day>7*86400000||checked===null||weak===null||weak>checked||required!==10||checked>10||h.independent_oos_verified!==false||h.live_trading_verified!==false)return {...unknown};
    const common={sourceDay:h.latest_official_day,advisory_only:true,independent_oos_verified:false,
      real_execution_verified:false,evaluated_windows:checked,underperforming_windows:weak};
    if(h.status===WEAK&&h.recommendation_mode==='research_only'&&checked===10&&weak===10){
      return {...common,mode:'research_only',status:WEAK,
        notice:'⚠ 策略績效警戒：截至 '+h.latest_official_day+'，五類選股的3日／7日觀察共10組全數未達標；候選僅供模擬研究，不是已驗證買點。',
        shortNotice:'短期績效10/10未達標・僅模擬'};
    }
    if(h.status==='SOME_OBSERVED_SHORT_HORIZONS_WEAK'&&checked===10&&weak>0&&weak<10){
      return {...common,mode:'review_before_using',status:h.status,
        notice:'⚠ 策略績效尚有 '+weak+'/10 組短期觀察未達標；請先核對風險，並非已驗證交易策略。',
        shortNotice:'部分策略績效未達標・僅觀察'};
    }
    if(h.status==='INSUFFICIENT_EVIDENCE'&&checked<10){
      return {...common,mode:'unverified',status:h.status,notice:unknown.notice,
        shortNotice:unknown.shortNotice};
    }
    return {...unknown};
  }
  function aiContext(feed){
    const s=summarize(feed);
    return {status:s.status,recommendation_mode:s.mode,
      observed_official_day:s.sourceDay,observed_windows:s.evaluated_windows,
      underperforming_windows:s.underperforming_windows,independent_oos_verified:false,
      broker_fill_verified:false,advisory_only:true,warning:s.notice};
  }
  function observationTag(feed,row){
    const s=summarize(feed);
    const marked=!!(row&&row.trade_readiness==='research_only');
    return {quality_mode:marked?'research_only':s.mode,
      source_observation_day:s.sourceDay,advisory_only:true,broker_fill_verified:false,
      label:marked||s.mode==='research_only'?'僅模擬研究（非買進建議）':s.shortNotice};
  }
  return {summarize,aiContext,observationTag};
});
