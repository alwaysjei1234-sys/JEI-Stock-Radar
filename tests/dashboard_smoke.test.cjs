const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('remote/index.html','utf8');
const scripts=[...html.matchAll(/<script\\b([^>]*)>([\\s\\S]*?)<\\/script>/gi)];
let checked=0;
for(const [,attrs,body] of scripts){
 if(/\\bsrc\\s*=/.test(attrs)||!body.trim())continue;
 new vm.Script(body,{filename:'remote/index.html inline script '+(++checked)});
}
assert.ok(checked>0,'dashboard inline scripts were not found');
for(const id of ['jeiPickSync','jeiPickOverview','jeiPickRows','jeiTargetPrice','jeiTargetReports','jeiTargetRun','jeiTargetResult']){
 assert.ok(new RegExp('\\bid=["\\']'+id+'["\\']').test(html),'missing dashboard control '+id);
}
assert.ok(html.includes('window.JEI_refreshPickPerformance=syncPicks'),'missing performance refresh entrypoint');
console.log('JEI dashboard inline JavaScript syntax and key controls verified:',checked);
