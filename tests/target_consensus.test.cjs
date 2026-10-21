const assert=require('node:assert/strict');
const {calc}=require('../remote/target_consensus.js');
const reports=[
 {broker:'甲',target:210,date:'2026-10-01'},
 {broker:'乙',target:250,date:'2026-09-01'},
 {broker:'丙',target:170,date:'2026-05-01'},
 {broker:'錯誤',target:'300',date:'2026-10-01'}
];
const r=calc({price:166.5,asOf:'2026-10-21',reports});
assert.equal(r.count,3);
assert.equal(r.mean,210);
assert.equal(r.median,210);
assert.equal(r.min,170);
assert.equal(r.max,250);
assert.ok(Math.abs(r.upsidePct-(210/166.5-1)*100)<1e-9);
assert.equal(r.staleCount,1);
assert.ok(r.warnings.includes('包含超過90日報告'));
assert.equal(calc({price:null,reports:[]}).upsidePct,null);
assert.equal(calc({price:100,reports:[]}).mean,null);
console.log('target consensus smoke tests passed');
