"""Offline official scheduled-calendar comparison; not an unscheduled closure audit.

Run from repository root:
  python docs/research/calendar-audit-20261105.py
Optional source inspection (no package installation or execution):
  python docs/research/calendar-audit-20261105.py --upstream-source PATH
The official annual table contains open-day markers; they are not holidays.
"""
import argparse
import ast
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.market_sessions import SCHEDULED_2026,UNSCHEDULED,closure_reason,next_expected_session
OPEN_MARKERS={'國曆新年開始交易日','農曆春節前最後交易日','農曆春節後開始交易日'}


def audit(reference):
    doc=reference['document']
    if doc.get('stat')!='ok' or doc.get('queryYear')!=2026 or doc.get('date')!='20260101':
        raise ValueError('Official annual response year/status is not verified')
    rows=doc['data']
    if len(rows)!=doc.get('total') or len({r[0]for r in rows})!=len(rows):
        raise ValueError('Incomplete or duplicate annual table')
    for row in rows:
        if date.fromisoformat(row[0]).isoformat()!=row[0] or not row[0].startswith('2026-'):
            raise ValueError('Invalid annual date')
    open_days={r[0]for r in rows if r[1]in OPEN_MARKERS}
    if len(open_days)!=3:raise ValueError('Open-day markers missing')
    closed={r[0]for r in rows if r[1]not in OPEN_MARKERS}
    weekday_closed={d for d in closed if date.fromisoformat(d).weekday()<5}
    jei_weekday={d for d in SCHEDULED_2026 if date.fromisoformat(d).weekday()<5}
    assert weekday_closed==jei_weekday,'Scheduled weekday closures differ from official table'
    daily_checked=0;daily_excluded=[];transitions_checked=0;transitions_excluded=[]
    for offset in range(365):
        day=date(2026,1,1)+timedelta(days=offset);key=day.isoformat()
        if key in UNSCHEDULED:daily_excluded.append(key)
        else:
            assert bool(closure_reason(day))==(day.weekday()>=5 or key in closed)
            daily_checked+=1
        candidate=day+timedelta(days=1)
        while candidate.weekday()>=5 or candidate.isoformat()in closed:candidate+=timedelta(days=1)
        if candidate.year!=2026:transitions_excluded.append({'from':key,'reason':'outside_verified_year'});continue
        interval=[(day+timedelta(days=i)).isoformat()for i in range(1,(candidate-day).days+1)]
        if any(d in UNSCHEDULED for d in interval):
            transitions_excluded.append({'from':key,'reason':'requires_independent_unscheduled_closure_evidence'});continue
        assert next_expected_session(day)==candidate.isoformat()
        transitions_checked+=1
    return {'scope':'2026_official_scheduled_calendar_only','source_url':reference['url'],
            'source_checked_at':reference['checked_at'],'raw_source_sha256':reference['sha256'],
            'official_rows':len(rows),'open_day_markers':sorted(open_days),
            'official_weekday_closures':sorted(weekday_closed),
            'jei_weekday_closures':sorted(jei_weekday),'scheduled_mismatches':[],
            'daily_classifications_checked':daily_checked,'daily_excluded_unscheduled':daily_excluded,
            'next_session_transitions_checked':transitions_checked,'next_session_exclusions':transitions_excluded,
            'limitations':['Annual table does not establish every unscheduled closure.',
                           'No 2027 opening or official quote/availability certification.',
                           'No OOS trading-performance qualification.']}


def inspect_upstream(path):
    raw=Path(path).read_bytes();tree=ast.parse(raw.decode())
    for node in tree.body:
        if isinstance(node,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='typhoons'for t in node.targets):
            values=ast.literal_eval(node.value.args[0]);days=[date.fromisoformat(d).isoformat()for d in values]
            return {'source_sha256':hashlib.sha256(raw).hexdigest(),
                    'static_typhoon_entries':len(days),'latest_static_typhoon_date':max(days),
                    'jei_exception_dates_absent_from_static_list':sorted(set(UNSCHEDULED)-set(days)),
                    'scope':'static_source_list_only_not_package_runtime'}
    raise ValueError('Named upstream typhoon list not found')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--upstream-source');args=parser.parse_args()
    ref=json.loads((ROOT/'docs/research/twse-calendar-reference-20261105.json').read_text())
    result=audit(ref)
    if args.upstream_source:result['upstream_static_review']=inspect_upstream(args.upstream_source)
    print(json.dumps(result,ensure_ascii=False,indent=2))
