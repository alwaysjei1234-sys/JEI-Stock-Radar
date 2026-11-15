'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('remote/index.html','utf8');
const names = [
 'validateJeiBackupHoldings',
 'validateJeiBackupAlertPrefs',
 'validateJeiBackupScreenPrefs',
 'validateJeiPrivateBackup',
 'parseJeiPrivateBackup'
];
function extract(name){
 const re=new RegExp('^function '+name+'\\([^]*?^\\}', 'm');
 const match=page.match(re);
 assert.ok(match, 'Missing private backup validator '+name);
 return match[0];
}
const declarations = [
 "const JEI_LOCAL_BACKUP_PREFIX='JEI-PRIVATE-BACKUP-V1:';",
 "const JEI_LOCAL_BACKUP_KIND='jei_private_local_migration';",
 "const JEI_SCREEN_BACKUP_FIELDS=['preset','score','price','rise','query','sector','order'];"
];
const context = vm.createContext({ });
vm.runInContext(declarations.join('\n')+'\n'+names.map(extract).join('\n'), context);
function call(name,...args){
 context.args = args;
 return vm.runInContext(name+'(...args)',context);
}
const sample={
 schema:1,kind:'jei_private_local_migration',
 holdings:[
  {code:'00937B',name:'月配 ETF',cost:15.6283,shares:44000,privateToken:'NEVER_EXPORT_TOKEN'},
  {code:'7711',name:'永擎',cost:257.8665,shares:2000}
 ],
 alertPrefs:{enabled:true,lossPct:8,gainPct:12,retracePct:5,api_key:'NEVER_EXPORT_TOKEN'},
 screenPrefs:{preset:'custom',score:'75',query:'散熱',backend_token:'NEVER_EXPORT_TOKEN'}
};
function fail(msg,fn){assert.throws(fn,msg)}
const safe=call('validateJeiPrivateBackup',sample);
assert.equal(safe.holdings.length,2);
assert.equal(safe.holdings[0].code,'00937B');
assert.equal(safe.holdings[0].cost,15.6283);
assert.equal(safe.holdings[0].shares,44000);
assert.equal(safe.alertPrefs.lossPct,8);
assert.equal(safe.screenPrefs.query,'散熱');
assert.ok(!JSON.stringify(safe).includes('NEVER_EXPORT_TOKEN'),'Never export private API/AI keys');
const wire='JEI-PRIVATE-BACKUP-V1:'+JSON.stringify(safe);
assert.equal(call('parseJeiPrivateBackup',wire).holdings.length,2);
assert.equal(call('parseJeiPrivateBackup',JSON.stringify(safe)).holdings.length,2);
fail(/invalid backup format/,()=>call('parseJeiPrivateBackup',JSON.stringify({...safe,kind:'other'})));
fail(/invalid backup length/,()=>call('parseJeiPrivateBackup',wire+' '.repeat(250000)));
fail(/invalid or duplicate holding/,()=>call('validateJeiPrivateBackup',{...safe,holdings:[safe.holdings[0],safe.holdings[0]]}));
for(const bad of [0,-1,Infinity,NaN,42.5]){
 fail(/invalid or duplicate holding/,()=>call('validateJeiPrivateBackup',{...safe,holdings:[{...safe.holdings[0],shares:bad}]}));
}
fail(/invalid holdings list/,()=>call('validateJeiPrivateBackup',{...safe,holdings:Array(501).fill(safe.holdings[0])}));
fail(/invalid alert settings/,()=>call('validateJeiPrivateBackup',{...safe,alertPrefs:{...safe.alertPrefs,lossPct:0}}));
fail(/invalid screen filter/,()=>call('validateJeiPrivateBackup',{...safe,screenPrefs:{preset:'x'.repeat(121)}}));
for(const name of ['exportJeiPrivateBackup','restoreJeiPrivateBackup']){
 const body=extract(name);
 assert.match(body,/JEI_PRIVATE_APP/,'Visitor must not export private holdings');
 assert.doesNotMatch(body,/fetch\(|XMLHttpRequest|sendBeacon|\.openUrl\(/,'Backup must never transmit positions');
}
const restore=extract('restoreJeiPrivateBackup');
assert.ok(restore.indexOf('window.confirm(')<restore.indexOf('localStorage.setItem('),'No restore before explicit confirmation');
assert.match(restore,/saved!==encoded/,'Must verify restored holdings roundtrip');
assert.match(restore,/catch\(e\)\{/,'Must not silently ignore failed restoration');
assert.ok(page.includes('id="migrationBackup"')&&page.includes('data-private-only id="localMigrationPanel"'));
assert.ok(page.includes('此備份不含 AI Key')&&page.includes('不要解除安裝舊 App'));
console.log('PASS on-device private migration backup: fidelity, secrets excluded, invalid/duplicate data rejected, explicit restore confirmation, no network export');
