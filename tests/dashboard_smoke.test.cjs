const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('remote/index.html','utf8');
const scripts=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
let checked=0;
for(const [,attrs,body] of scripts){
 if(/\bsrc\s*=/.test(attrs)||!body.trim())continue;
 new vm.Script(body,{filename:'remote/index.html inline script '+(++checked)});
}
assert.ok(checked>0,'dashboard inline scripts were not found');
for(const id of ['jeiPickSync','jeiPickOverview','jeiPickRows','jeiPickDetails','jeiPickDetailsSummary']){
 assert.ok(html.includes('id="'+id+'"')||html.includes("id='"+id+"'"),'missing dashboard control '+id);
}
for(const id of ['jeiTargetPrice','jeiTargetReports','jeiTargetRun','jeiTargetResult']){
 assert.ok(!html.includes('id="'+id+'"')&&!html.includes("id='"+id+"'"),'manual-only broker research form must stay removed: '+id);
}
assert.ok(html.includes('Automatic verified-data panels will replace them after source integration'),'unavailable broker data must not be fabricated');
assert.ok(html.includes('window.JEI_refreshPickPerformance=syncPicks'),'missing performance refresh entrypoint');
assert.ok(html.includes('if(Number(v.completed)<=0)continue;'),'unmatured windows must not appear as zero-performance rows');
assert.ok(html.includes('未到期不列為 0%'),'unmatured windows must be clearly labeled');
assert.ok(html.includes('<details id="jeiPickDetails"'),'performance breakdown should be collapsed by default');
console.log('JEI dashboard inline JavaScript syntax and key controls verified:',checked);
