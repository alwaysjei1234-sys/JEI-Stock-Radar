const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const quality=require('../remote/strategy_integration.js');

function feed(status='ALL_OBSERVED_SHORT_HORIZONS_WEAK'){
 return {
  data_date:'2026-11-18',market:{mode:'盤中即時',stale:false},
  strategy_health:{
   source:'forward_official_close_pick_validation',status,
   recommendation_mode:status==='ALL_OBSERVED_SHORT_HORIZONS_WEAK'?'research_only':'review_before_using',
   evaluated_windows:10,underperforming_windows:status==='ALL_OBSERVED_SHORT_HORIZONS_WEAK'?10:3,
   required_windows:10,latest_official_day:'2026-11-17',
   independent_oos_verified:false,live_trading_verified:false
  }
 };
}
{
 const input=feed(),before=JSON.stringify(input);
 const x=quality.summarize(input);
 assert.equal(x.mode,'research_only');
 assert.match(x.notice,/10組全數未達標/);
 assert.match(x.notice,/僅供模擬研究/);
 assert.equal(x.advisory_only,true);
 assert.equal(x.independent_oos_verified,false);
 assert.equal(x.real_execution_verified,false);
 const ai=quality.aiContext(input);
 assert.equal(ai.recommendation_mode,'research_only');
 assert.equal(ai.observed_official_day,'2026-11-17');
 assert.equal(ai.underperforming_windows,10);
 assert.equal(ai.broker_fill_verified,false);
 const row=quality.observationTag(input,{code:'3017',trade_readiness:'research_only'});
 assert.equal(row.quality_mode,'research_only');
 assert.match(row.label,/非買進建議/);
 assert.equal(JSON.stringify(input),before,'shared advisory cannot change the source feed');
}
{
 const mixed=quality.summarize(feed('SOME_OBSERVED_SHORT_HORIZONS_WEAK'));
 assert.equal(mixed.mode,'review_before_using');
 assert.equal(mixed.underperforming_windows,3);
 assert.doesNotMatch(mixed.notice,/全數未達標/);
}
for(const invalid of [
 null,{}, {data_date:'2026-11-18'},
 {...feed(),strategy_health:{...feed().strategy_health,underperforming_windows:11}},
 {...feed(),strategy_health:{...feed().strategy_health,source:'unsupported'}},
 {...feed(),strategy_health:{...feed().strategy_health,latest_official_day:'2026-11-19'}},
 {...feed(),strategy_health:{...feed().strategy_health,latest_official_day:'2026-02-30'}},
 {...feed(),strategy_health:{...feed().strategy_health,latest_official_day:'2026-11-01'}},
 {...feed(),strategy_health:{...feed().strategy_health,independent_oos_verified:true}},
 {...feed(),strategy_health:{...feed().strategy_health,evaluated_windows:9}},
 {...feed(),strategy_health:{...feed().strategy_health,required_windows:9}},
]){
 const x=quality.summarize(invalid);
 assert.equal(x.mode,'unverified',JSON.stringify(invalid));
 assert.equal(x.independent_oos_verified,false);
 assert.doesNotMatch(x.notice,/全數未達標/);
}
{
 const nativeRow={code:'3017',trade_readiness:'research_only'};
 const fallback=quality.observationTag({data_date:'2026-11-18'},nativeRow);
 assert.equal(fallback.quality_mode,'research_only',
    'an explicit research-only candidate may not be relabeled actionable by missing shared state');
}
for(const file of ['remote/index.html','remote/cash.html','remote/paper.html']){
 const html=fs.readFileSync(file,'utf8');
 assert.match(html,/<script src="\.\/strategy_integration\.js"><\/script>/,
   file+' must load the shared JS module');
 const inline=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
   .filter(([,attrs,body])=>!/\bsrc\s*=/.test(attrs)&&body.trim());
 for(const [,attrs,body] of inline)new vm.Script(body,{filename:file});
 assert.ok(inline.length>0);
}
const home=fs.readFileSync('remote/index.html','utf8');
assert.match(home,/id="strategyIntegrationStatus"/);
assert.match(home,/renderStrategyIntegration\(\);/);
assert.match(home,/JEIStrategyIntegration\?\.aiContext\(system\)/);
assert.match(home,/el\.dataset\.qualityMode=summary\.mode/);
for(const file of ['remote/cash.html','remote/paper.html']){
 const html=fs.readFileSync(file,'utf8');
 assert.match(html,/id="strategyQualityStatus"/,file);
 assert.match(html,/JEIStrategyIntegration\?\.summarize\(feed\)/,file);
 assert.match(html,/quality_mode:quality\.mode/,file);
 assert.match(html,/quality\.shortNotice/,file);
 assert.doesNotMatch(html,/\b(\bautoTrade\b|\bplaceOrder\b)\(/,file);
}
const api=fs.readFileSync('api/consult.js','utf8');
assert.match(api,/context\.strategy_quality/);
assert.match(api,/research_only/);
const real=JSON.parse(fs.readFileSync('remote/system.json','utf8'));
if(real.strategy_health&&real.strategy_health.status==='ALL_OBSERVED_SHORT_HORIZONS_WEAK'){
 const s=quality.summarize(real);
 assert.equal(s.mode,'research_only',
   'currently published weak strategy should flow through the shared module');
}
console.log('JEI integration passed: dashboard + multi-AI + paper + cash share dated risk evidence; no filled trades invented');
