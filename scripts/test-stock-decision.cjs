#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {analyze}=require('../remote/stock_decision.js');
const t=analyze({price:316.5,support:277.5,resistance:298.5,asof:'2026-10-21',flowDate:'2026-10-20'});
assert.equal(t.state,'broken_resistance');
assert.equal(t.resistanceLabel,'已突破的原壓力');
assert.equal(t.flowFresh,false);
assert.equal(t.resistanceDistancePct,-5.69);
assert.equal(analyze({price:98.4,support:83.3,resistance:95.7}).state,'broken_resistance');
assert.equal(analyze({price:75,support:83.3,resistance:95.7}).state,'below_support');
assert.equal(analyze({price:90,support:83.3,resistance:95.7}).state,'in_range');
assert.equal(analyze({price:NaN,support:83.3}).state,'missing_price');
assert.equal(analyze({price:100}).state,'unverified');
assert.equal(analyze({price:100,asof:'2026-10-21',flowDate:'2026-10-21'}).flowFresh,true);
console.log('PASS: JEI stock decision regression scenarios');
