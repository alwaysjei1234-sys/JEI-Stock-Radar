import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const read = p => fs.readFileSync(p,'utf8');
const htmls = ['remote/index.html','remote/cash.html','remote/paper.html'];
for (const path of htmls) {
 const src=read(path),scripts=[...src.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
 assert(scripts.length>0,path+' has no script');
 for (const [i,script] of scripts.entries()) new vm.Script(script[1],{filename:path+'#script'+i});
 console.log('PASS JavaScript parse:',path);
}
const main=read('remote/index.html');
for (const id of ['marketState','cashLevel','totalPnl','portfolioRisk','riskReasons','riskExpand','screenPreset','screenPriceMax','screenRiseMax','attackList','holdingsGrid','webRecoList','tomorrowMonsterList']) {
 assert(main.includes('id="'+id+'"'),'missing UI ID '+id);
}
assert(main.includes('function toggleRiskDetails()'));
assert(main.includes("const UI_VERSION='3.9.2-mobile-brief'"));
assert(main.includes("const DEFAULT_HOLDINGS=[]"),'public portfolio leak regression');
assert(main.includes('function renderAttackScreener()'));
assert(main.includes('function renderWebReco()'));
assert(main.includes("const safe=escapeMarketText"),'network recommendations must be escaped');
console.log('PASS dashboard/screener/security anchors');
const cash=read('remote/cash.html'),paper=read('remote/paper.html');
for(const html of [cash,paper]){
 assert(html.includes("const JEI_STATIC_PENDING={}"));
 assert(html.includes("readJeiStatic('system')"));
 assert(html.includes("JEINative.fetchStaticJson(kind)"));
}
assert(cash.includes("readJeiStatic('daily')"));
assert(cash.includes("readJeiStatic('performance')"));
assert(cash.includes('id="cloudRows"'));
assert(cash.includes("mode==='今日收盤'"));
assert(cash.includes('jei-cash-auto-watch-v1'));
assert(paper.includes('jei-paper-auto-watch-v1'));
assert(cash.includes("const KEY='jei-cash-trades-v1'"));
assert(paper.includes("const KEY='jei-paper-trades-v1'"));
console.log('PASS cash/day-trading isolation and native feed bridge');
const java=read('app/src/main/java/com/jei/stockradar/MainActivity.java');
for(const token of ['private void loadRemotePage(', 'private void fetchStaticJson(', 'private void jsStatic(', 'private boolean validStatic(', 'private String getRemoteStatic(', '/remote/daily_prices.json', '"/remote/cash.html"', '"/remote/paper.html"']) {
 assert(java.includes(token),'Android bridge missing '+token);
}
const feed=JSON.parse(read('remote/system.json')),days=JSON.parse(read('remote/daily_prices.json')),manifest=JSON.parse(read('remote/update.json'));
assert(feed.market && typeof feed.data_date==='string');
assert(days.schema===1&&days.kind==='official_daily_close'&&typeof days.days==='object');
const gradle=read('app/build.gradle');
const code=Number(gradle.match(/versionCode\s+(\d+)/)?.[1]);
const name=gradle.match(/versionName\s+'([^']+)'/)?.[1];
assert(Number.isSafeInteger(code)&&name);
assert(manifest.versionCode<=code,'Manifest must never advertise a newer unbuilt APK');
if(manifest.versionCode===code)assert(manifest.versionName.startsWith(name),'Published APK version name must match Gradle');
console.log('PASS feed schema and version compatibility; Android='+name+' (code '+code+')');
