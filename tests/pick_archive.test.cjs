const assert=require('node:assert/strict');
const fs=require('node:fs');
const data=JSON.parse(fs.readFileSync('remote/pick_validation.json','utf8'));
assert.ok(Array.isArray(data.picks),'missing frozen picks');
assert.equal(data.total_frozen_picks,data.picks.length,'archive count mismatch');
assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(data.latest_official_day),'missing official day');
const ledger=JSON.parse(fs.readFileSync('remote/pick_history.json','utf8'));
assert.ok(Array.isArray(ledger.picks),'missing immutable pick ledger');
assert.equal(ledger.picks.length,data.picks.length,'report must include every frozen ledger pick');
const ledgerIds=new Set(ledger.picks.map(p=>p.id));
const ledgerById=new Map(ledger.picks.map(p=>[p.id,p]));
for(const pick of data.picks){
 const source=ledgerById.get(pick.id);
 assert.ok(source,'published pick missing in ledger: '+pick.id);
 for(const field of ['day','group','rank','code','name','score','signal_close','origin']){
  assert.deepEqual(pick[field],source[field],'archived recommendation was altered: '+pick.id+'/'+field);
 }
}

assert.equal(ledgerIds.size,ledger.picks.length,'duplicate frozen ledger identity');
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
assert.deepEqual([...ids].sort(),[...ledgerIds].sort(),'report and ledger identities differ');
const official=JSON.parse(fs.readFileSync('remote/daily_prices.json','utf8'));
assert.equal(official.kind,'official_daily_close','unverified daily close archive');
for(const pick of data.picks){
 const signal=official.days?.[pick.day]?.[pick.code];
 assert.ok(Number.isFinite(signal)&&signal>0,'missing official signal close: '+pick.id);
 assert.equal(signal,pick.signal_close,'signal close differs from official archive: '+pick.id);
 for(const outcome of pick.outcomes){
  if(outcome.status!=='complete')continue;
  const settlement=official.days?.[outcome.end_day]?.[pick.code];
  assert.ok(Number.isFinite(settlement)&&settlement>0,'missing official exit close: '+pick.id);
  assert.ok(Math.abs(settlement/outcome.end_close-1)<1e-9,'settlement close differs from archive: '+pick.id);
 }
}
const costs=data.estimated_costs;
assert.ok(costs&&Number.isFinite(costs.buy_fee)&&Number.isFinite(costs.sell_fee)&&Number.isFinite(costs.sell_tax),'missing simulation costs');
for(const pick of data.picks){
 for(const outcome of pick.outcomes){
  if(outcome.status!=='complete')continue;
  const net=100*(outcome.end_close*(1-costs.sell_fee-costs.sell_tax)/(pick.signal_close*(1+costs.buy_fee))-1);
  assert.ok(Math.abs(net-outcome.estimated_net_return_pct)<=0.00051,'net return formula mismatch: '+pick.id);
  const gross=100*(outcome.end_close/pick.signal_close-1);
  assert.ok(Math.abs(gross-outcome.gross_return_pct)<=0.00051,'gross return formula mismatch: '+pick.id);
 }
}
for(const [group,byHorizon] of Object.entries(data.groups)){
 for(const [horizon,summary] of Object.entries(byHorizon)){
  const returns=data.picks.filter(p=>p.group===group)
   .flatMap(p=>p.outcomes.filter(o=>o.trading_days===Number(horizon)&&o.status==='complete'))
   .map(o=>o.estimated_net_return_pct).sort((a,b)=>a-b);
  if(!returns.length)continue;
  const round=(v,n)=>Number(v.toFixed(n));
  const wins=returns.filter(v=>v>0).length;
  const avg=returns.reduce((a,b)=>a+b,0)/returns.length;
  const mid=Math.floor(returns.length/2);
  const median=returns.length%2?returns[mid]:(returns[mid-1]+returns[mid])/2;
  assert.ok(Math.abs(summary.win_rate_pct-round(100*wins/returns.length,2))<=0.01,'win rate mismatch: '+group+'/'+horizon);
  assert.ok(Math.abs(summary.avg_estimated_net_pct-round(avg,3))<=0.001,'average return mismatch: '+group+'/'+horizon);
  assert.ok(Math.abs(summary.median_estimated_net_pct-round(median,3))<=0.001,'median return mismatch: '+group+'/'+horizon);
  assert.equal(summary.best_estimated_net_pct,returns[returns.length-1],'best return mismatch: '+group+'/'+horizon);
  assert.equal(summary.worst_estimated_net_pct,returns[0],'worst return mismatch: '+group+'/'+horizon);
 }
}
const officialDates=Object.entries(official.days)
 .filter(([date,quotes])=>/^\d{4}-\d{2}-\d{2}$/.test(date)&&Object.values(quotes).filter(v=>Number.isFinite(v)&&v>0).length>=500)
 .map(([date])=>date).sort();
assert.equal(data.latest_official_day,officialDates[officialDates.length-1],'performance report lags official price archive');
for(const pick of data.picks){
 const signalIndex=officialDates.indexOf(pick.day);
 assert.ok(signalIndex>=0,'signal date not found in official trading calendar: '+pick.id);
 for(const outcome of pick.outcomes){
  const expectedIndex=signalIndex+outcome.trading_days;
  if(expectedIndex>=officialDates.length){
   assert.equal(outcome.status,'pending','unmatured horizon must remain pending: '+pick.id);
  }else{
   assert.equal(outcome.end_day,officialDates[expectedIndex],'incorrect future trading-day settlement: '+pick.id);
  }
 }
}
const allowedGroups=new Set(['attack','next','monster','tomorrow_monster','future_monster']);
const expectedHorizons=[3,7,15,20,30,40,60];
assert.deepEqual([...horizons].sort((a,b)=>a-b),expectedHorizons,'incorrect trading-day horizons');
for(const pick of data.picks){
 assert.ok(allowedGroups.has(pick.group),'unknown strategy group');
 assert.ok(Number.isInteger(pick.rank)&&pick.rank>=1&&pick.rank<=5,'invalid frozen ranking');
 assert.ok(/^\d{4}$/.test(pick.code),'invalid Taiwan stock code');
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
   for(const field of ['win_rate_pct','avg_estimated_net_pct','median_estimated_net_pct','best_estimated_net_pct','worst_estimated_net_pct']){
    assert.equal(summary[field],null,'no completed picks must not show '+field);
   }
  }
 }
}
console.log('JEI frozen picks verified:',data.picks.length);
