const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('remote/brief.html','utf8');
const nodes=new Map();
const context={document:{getElementById(id){if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:true});return nodes.get(id)}},fetch:()=>new Promise(()=>{}),URL,Intl,Date};
vm.createContext(context);
for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))vm.runInContext(match[1],context);
const row={date:'2026-11-04',edition:'close',checked_at:'2026-11-04T19:15:51+08:00',status:'accepted',delivery_confirmed:true,token:'SECRET'};
const doc={schema:1,editions:{close:row}};
let text=context.lineStatusText(doc,'close','2026-11-05');
assert.match(text,/歷史紀錄/);assert.match(text,/API 已接受/);assert.match(text,/手機實收尚未確認/);assert.ok(!text.includes('SECRET'));
assert.match(context.lineStatusText(doc,'morning','2026-11-05'),/尚無可核對/);
row.status='failed';assert.match(context.lineStatusText(doc,'close','2026-11-04'),/今日紀錄.*發送失敗/);
row.status='already_accepted';assert.match(context.lineStatusText(doc,'close','2026-11-04'),/未重複發送/);
row.edition='close_unavailable';assert.match(context.lineStatusText(doc,'close','2026-11-04'),/資料異常通知/);
row.status='delivered';assert.match(context.lineStatusText(doc,'close','2026-11-04'),/尚無可核對/);
row.status='__proto__';assert.match(context.lineStatusText(doc,'close','2026-11-04'),/尚無可核對/);
console.log('LINE status UI: history, missing evidence, failure, duplicate, notice and untrusted delivery checks passed');

row.edition='close';row.status='quota_blocked';row.http_status=429;
row.accepted_attempt={date:row.date,edition:'close',checked_at:'2026-11-04T18:15:00+08:00',status:'accepted',http_status:200,evidence_url:'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/123',token:'SECRET'};
text=context.lineStatusText(doc,'close','2026-11-04');
assert.match(text,/免費額度安全檢查未通過/);assert.match(text,/先前已獲 API 接受/);assert.match(text,/手機實收尚未確認/);assert.ok(!text.includes('SECRET'));
for(const change of [{date:'2026-11-03'},{edition:'close_unavailable'},{http_status:500},{evidence_url:'https://evil.example/123'},{checked_at:'2026-11-04T23:00:00+08:00'}]){
 const saved=row.accepted_attempt;row.accepted_attempt={...saved,...change};
 assert.ok(!context.lineStatusText(doc,'close','2026-11-04').includes('先前已獲 API 接受'));
 row.accepted_attempt=saved;
}
console.log('LINE status UI: latest failed attempt and same-day acceptance both visible; invalid acceptance excluded');

const policy={record_kind:'policy_check',date:'2026-11-05',edition:'close',checked_at:'2026-11-05T02:37:55+08:00',status:'policy_skipped',policy_code:'dispatch_window_not_open',evidence_url:'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/123',api_accepted:true,reason:'SECRET'};
doc.policy_checks={close:policy};
text=context.lineStatusText(doc,'close','2026-11-05');
assert.match(text,/本次未發送/);assert.match(text,/本日發送時段未開始/);assert.match(text,/不是 API 發送嘗試/);assert.ok(!text.includes('SECRET'));
assert.match(context.lineStatusText({schema:1,policy_checks:{close:policy}},'close','2026-11-05'),/尚無可核對.*本次未發送/);
for(const change of [{policy_code:'__proto__'},{edition:'morning'},{checked_at:'invalid'},{evidence_url:'https://evil.example/'}]){
 doc.policy_checks.close={...policy,...change};assert.ok(!context.lineStatusText(doc,'close','2026-11-05').includes('排程檢查'));
}
console.log('LINE policy UI: skip reasons remain separate from API acceptance and reject untrusted fields');

doc.policy_checks.close=policy;
const olderAttempt=doc.editions.close;doc.editions.close={...olderAttempt,checked_at:'2026-11-05T19:10:00+08:00'};
assert.ok(!context.lineStatusText(doc,'close','2026-11-05').includes('排程檢查'));
doc.editions.close=olderAttempt;

doc.policy_checks.close={...policy,policy_code:'brief_failed_before_send'};
assert.match(context.lineStatusText(doc,'close','2026-11-05'),/報告產生或發布未完成.*不是 API 發送嘗試/);
