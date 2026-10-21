const assert=require('node:assert/strict');
const fs=require('node:fs');
const data=JSON.parse(fs.readFileSync('remote/pick_validation.json','utf8'));
assert.ok(Array.isArray(data.picks),'missing frozen picks');
assert.equal(data.total_frozen_picks,data.picks.length,'archive count mismatch');
assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(data.latest_official_day),'missing official day');
const ids=new Set();
const horizons=new Set(data.horizons_trading_days);
for(const pick of data.picks){
 assert.ok(pick&&typeof pick.id==='string'&&pick.id.length>0,'missing id');
 assert.ok(!ids.has(pick.id),'duplicate id: '+pick.id);
 ids.add(pick.id);
 assert.equal(pick.id,[pick.day,pick.group,pick.code].join(':'),'identity mismatch');
 assert.ok(pick.day<=data.latest_official_day,'future-dated signal');
 assert.ok(Number.isFinite(pick.signal_close)&&pick.signal_close>0,'invalid entry close');
 assert.ok(Array.isArray(pick.outcomes),'missing outcomes');
 assert.equal(pick.outcomes.length,horizons.size,'horizon count mismatch');
 const seen=new Set();
 for(const o of pick.outcomes){
  assert.ok(horizons.has(o.trading_days),'unknown horizon');
  assert.ok(!seen.has(o.trading_days),'duplicate horizon');
  seen.add(o.trading_days);
  assert.ok(['complete','pending','missing_price'].includes(o.status),'invalid status');
  if(o.status==='complete'){
   assert.ok(Number.isFinite(o.estimated_net_return_pct),'missing net return');
   assert.ok(o.end_day>pick.day&&o.end_day<=data.latest_official_day,'invalid settlement date');
   assert.ok(Number.isFinite(o.end_close)&&o.end_close>0,'missing settlement close');
  }else{
   assert.equal(o.estimated_net_return_pct??null,null,'unfinished outcome has realized return');
  }
 }
}
for(const [group,byHorizon] of Object.entries(data.groups)){
 for(const [horizon,summary] of Object.entries(byHorizon)){
  const records=data.picks.filter(p=>p.group===group).map(p=>p.outcomes.find(o=>o.trading_days===Number(horizon)));
  assert.ok(records.every(Boolean),'missing outcome for '+group+'/'+horizon);
  for(const [state,key] of [['complete','completed'],['pending','pending'],['missing_price','missing_price']]){
   assert.equal(summary[key],records.filter(o=>o.status===state).length,'incorrect '+key+' for '+group+'/'+horizon);
  }
  const total=summary.completed+summary.pending+summary.missing_price;
  assert.equal(total,records.length,'unaccounted picks for '+group+'/'+horizon);
  const finished=records.filter(o=>o.status==='complete');
  if(!finished.length){
   assert.equal(summary.win_rate_pct,null,'no completed picks must not show a win rate');
   assert.equal(summary.avg_estimated_net_pct,null,'no completed picks must not show a return');
  }
 }
}
console.log('JEI frozen picks verified:',data.picks.length);
