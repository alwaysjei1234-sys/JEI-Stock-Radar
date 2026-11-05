"""Public-only prospective evidence. Never classifies a trade as verified OOS."""
import argparse
import copy
from datetime import date,datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo('Asia/Taipei')
RULE_FILES=(
    'scripts/update_system.py','scripts/update_paper_performance.py',
    'scripts/pattern_signals.py','scripts/corporate_actions.py',
    'scripts/market_sessions.py','scripts/paper_evidence.py',
    'scripts/paper_provenance.py','.github/workflows/update-paper-performance.yml',
)
FIELDS={'schema','version','recorded_at','snapshot_sha256','source_commit',
        'source_dirty','reconstructed','qualification'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def rule_spec(root,settings):
    root=Path(root)
    files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in RULE_FILES}
    spec={'schema':1,'model':'official_daily_close_paper_observation',
          'settings':copy.deepcopy(settings),'files':files}
    return {**spec,'version':digest(spec)}


def git_context(root):
    try:
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=3).strip()
        dirty=subprocess.check_output(['git','status','--porcelain','--',*RULE_FILES],
            cwd=root,text=True,timeout=3)
        if not re.fullmatch(r'[0-9a-f]{40}',sha):raise ValueError('Invalid source ref')
        return sha,bool(dirty.strip())
    except (OSError,ValueError,subprocess.SubprocessError):
        return None,True


def capture(feed,day,signals,settings,now=None,root=ROOT):
    now=now or datetime.now(TZ)
    if now.tzinfo is None:raise ValueError('Evidence timestamp requires timezone')
    now=now.astimezone(TZ)
    if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:
        raise ValueError('Invalid signal day')
    if feed.get('data_date')!=day:raise ValueError('Snapshot date mismatch')
    market=feed.get('market')or{}
    # The hash input is allowlisted. In particular it excludes holdings, costs,
    # account data, environment values and arbitrary extra feed properties.
    snapshot={'data_date':day,'updated_at':feed.get('updated_at'),
              'mode':market.get('mode'),'close_count':market.get('close_count'),
              'signals':[{key:row.get(key) for key in ('code','day','signal_close','score','source')}
                         for row in signals]}
    spec=rule_spec(root,settings)
    sha,dirty=git_context(root)
    return copy_record({'schema':1,'version':spec['version'],
        'recorded_at':now.isoformat(timespec='seconds'),'snapshot_sha256':digest(snapshot),
        'source_commit':sha,'source_dirty':dirty,
        'reconstructed':now.date().isoformat()!=day,'qualification':'provenance_only'})


def copy_record(value):
    if value is None:return None
    if (not isinstance(value,dict)or set(value)!=FIELDS or type(value['schema'])is not int
            or value['schema']!=1 or value['qualification']!='provenance_only'):
        raise ValueError('Invalid public paper provenance')
    for key in ('version','snapshot_sha256'):
        if not isinstance(value[key],str)or not re.fullmatch(r'[0-9a-f]{64}',value[key]):
            raise ValueError('Invalid evidence digest')
    sha=value['source_commit']
    if sha is not None and (not isinstance(sha,str)or not re.fullmatch(r'[0-9a-f]{40}',sha)):
        raise ValueError('Invalid evidence source')
    if sha is None and value['source_dirty'] is False:
        raise ValueError('Missing source cannot claim a clean checkout')
    if any(type(value[k])is not bool for k in ('source_dirty','reconstructed')):
        raise ValueError('Invalid evidence flags')
    try:
        stamp=datetime.fromisoformat(value['recorded_at'])
        if stamp.tzinfo is None:raise ValueError('Timezone required')
    except (TypeError,ValueError):raise ValueError('Invalid evidence timestamp')from None
    return copy.deepcopy(value)


def register(spec,effective_from,path,now):
    if now.tzinfo is None:raise ValueError('Registration timestamp requires timezone')
    now=now.astimezone(TZ)
    start=date.fromisoformat(effective_from)
    if start.isoformat()!=effective_from or start<=now.date():
        raise ValueError('Registration must precede the first observation date')
    document={'schema':1,'declared_at':now.isoformat(timespec='seconds'),
              'effective_from':effective_from,'qualification':'protocol_registration_only',
              'rules':spec,'note':'Published protocol and record hashes need independent audit; no OOS qualification is granted.'}
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation: later runs may not rewrite an earlier declaration.
    with path.open('x',encoding='utf-8')as stream:
        stream.write(json.dumps(document,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--effective-from',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    from scripts.update_paper_performance import provenance_settings
    register(rule_spec(ROOT,provenance_settings()),args.effective_from,args.output,datetime.now(TZ))
    print('Future paper protocol saved; OOS qualification unchanged')


if __name__=='__main__':main()
