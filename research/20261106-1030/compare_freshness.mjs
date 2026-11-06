import {readFileSync,writeFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import {createHash} from 'node:crypto';
const base=new URL('./',import.meta.url);
const source=readFileSync(new URL('cli_src_commands_stock_quote-status.ts',base),'utf8');
const hash=createHash('sha256').update(source).digest('hex');
if(hash!=='ff62d6a057fe9bfa38c5c55f42718347e210b7e444449f16969528f176d7479e')throw Error('Unreviewed source');
// Isolate the pure functions: the sole import is TStock, used only as a type.
const js=stripTypeScriptTypes(source.replace(/^import \{ TStock \} from '@\/types\/stock'\r?\n/,''));
const {quoteStatus,quoteTimestamp}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
const now=new Date('2026-11-06T02:30:00Z');
const baseQuote={c:'2330',ex:'tse',ch:'2330.tw',d:'20261106',t:'10:29:55',z:'100',y:'99',v:'50'};
const cases=[['fresh',{},'今日成交'],['stale_same_day',{t:'09:00:00'},'今日成交'],['future_clock_same_day',{t:'11:00:00'},'今日成交'],['missing_time',{t:'-'},'今日成交'],['zero_price',{z:'0'},'今日成交'],['previous_day',{d:'20261105'},'前期成交'],['future_date',{d:'20261109'},'日期異常'],['no_trade',{z:'-'},'無成交價']];
const result=cases.map(([name,changes,expected])=>{const quote={...baseQuote,...changes};const status=quoteStatus(quote,now);if(status!==expected)throw Error(name);return {name,quote,cli_status:status,cli_timestamp:quoteTimestamp(quote)}});
writeFileSync(new URL('freshness-cases.json',base),JSON.stringify({source_sha256:hash,now:now.toISOString(),cases:result},null,2));
console.log('8 isolated original quote-status cases passed; date label is not an age gate');
