const fs=require('node:fs');const assert=require('node:assert/strict');const html=fs.readFileSync('remote/index.html','utf8');const py=fs.readFileSync('scripts/update_system.py','utf8');const manifest=fs.readFileSync('app/src/main/AndroidManifest.xml','utf8');const activity=fs.readFileSync('app/src/main/java/com/jei/stockradar/MainActivity.java','utf8');
function check(label,fn){try{fn();console.log('PASS',label)}catch(e){console.error('FAIL',label,e.message);process.exitCode=1}}
check('Public page guards private routes',()=>{assert.match(html,/function go\(id\)\{if\(!JEI_PRIVATE_APP/);assert.match(html,/function loadHoldings\(\)\{if\(!JEI_PRIVATE_APP/)});
check('No public portfolio nodes removed (prevents JS null dereference)',()=>assert.doesNotMatch(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>el\.remove\(\)\)/));
check('Public feed strips private positions',()=>{assert.match(py,/if out\.get\("holdings"\):/);assert.match(html,/system\.holdings=JEI_PRIVATE_APP\?/)});
check('Android backups disabled',()=>assert.match(manifest,/android:allowBackup="false"/));
check('WebView file-origin crossing disabled',()=>{assert.match(activity,/setAllowFileAccessFromFileURLs\(false\)/);assert.match(activity,/setAllowUniversalAccessFromFileURLs\(false\)/)});
check('Stock screener and heatmap wired',()=>{assert.match(html,/function renderAttackScreener\(/);assert.match(html,/function renderSectorHeatmap\(/);assert.match(html,/renderSectors\(\);renderSectorHeatmap\(\)/)});
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(Boolean);const vm=require('node:vm');check('Inline JavaScript syntax',()=>{for(const code of scripts)new vm.Script(code)});

check('Trading hours use Asia/Taipei timezone',()=>assert.match(html,/function tradingWindow\(\).*timeZone:'Asia\/Taipei'/));
check('Screener updates freshness label',()=>assert.match(html,/function renderAttackScreener\(\)\{updateFeedFreshness\(\)/));
check('Private sections are hidden without removal',()=>assert.match(html,/querySelectorAll\('#hold,#rotate'\)\.forEach\(el=>\{el\.style\.display='none'/));

check('WebView external links open outside app',()=>assert.ok(activity.includes('shouldOverrideUrlLoading')&&activity.includes('Intent.ACTION_VIEW')));
check('Mixed content blocked',()=>assert.ok(activity.includes('MIXED_CONTENT_NEVER_ALLOW')));

check('Sector dropdown is wired into stock screening',()=>assert.ok(html.includes('id="screenSector"')&&html.includes('function syncScreenSectors()')&&html.includes("'screenSector','screenOrder'")));

check('Ranking cards escape untrusted market fields',()=>assert.ok(html.includes('function escapeMarketText(value)')&&html.includes('safe(x.name)')&&html.includes('safe(x.reason||x.status)')));

check('Feed date uses timezone-safe calendar parts',()=>assert.ok(html.includes('function updateFeedFreshness()')&&html.includes('formatToParts(now)')&&html.includes('dp.year')));

check('Market text escaping blocks HTML injection at runtime',()=>{
 const line=html.split('\n').find(x=>x.startsWith('function escapeMarketText('));
 assert.ok(line,'escape helper missing');
 const ctx={};vm.runInNewContext(line+';globalThis.testEscape=escapeMarketText;',ctx);
 assert.equal(ctx.testEscape('<img src=x onerror="alert(1)">'),'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
 assert.equal(ctx.testEscape('A&B'), 'A&amp;B');
 assert.equal(ctx.testEscape(null),'');
});
check('Taiwan trading hours are timezone-independent at runtime',()=>{
 const line=html.split('\n').find(x=>x.startsWith('function tradingWindow('));
 assert.ok(line,'trading window helper missing');
 const ctx={Date:class extends Date{constructor(){super('2026-10-13T01:00:00Z')}} ,Intl};
 vm.runInNewContext(line+';globalThis.testTrading=tradingWindow;',ctx);
 assert.equal(ctx.testTrading(),true,'Tuesday 09:00 Taipei must be trading');
 ctx.Date=class extends Date{constructor(){super('2026-10-13T07:00:00Z')}};
 assert.equal(ctx.testTrading(),false,'Tuesday 15:00 Taipei must be closed');
});
