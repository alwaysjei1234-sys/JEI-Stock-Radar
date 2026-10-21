const assert=require('node:assert/strict');
const {evaluate,summarize}=require('../remote/forecast_audit.js');
const f={date:'2025-10-21',target:120,months:12};
assert.equal(evaluate(f,[{date:'2026-03-01',close:125}],'2026-10-21').state,'hit');
assert.equal(evaluate(f,[{date:'2026-01-02',close:100}],'2026-04-01').state,'pending');
assert.equal(evaluate(f,[],'2026-10-21').state,'missing_price');
assert.equal(evaluate({date:'bad',target:120},[],'2026-10-21').state,'invalid');
assert.equal(summarize([{state:'hit',hit:true},{state:'miss',hit:false},{state:'pending'}]).hitRate,0.5);
console.log('forecast audit smoke tests passed');
