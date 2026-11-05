"""Synthetic boundary check against the checked main's public quarterly records.
Run: python path/to/cache_boundaries.py /path/to/JEI-Stock-Radar
No network, strategy change, real credentials or production mutation.
"""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timedelta
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from scripts.update_working_capital import retained_record
source=json.loads((root/'remote/working_capital.json').read_text());checks=[]
for code,old in source['records'].items():
 observed=datetime.fromisoformat(old['observed_at'])
 for age,allowed in [(0,True),(7*86400,True),(7*86400+1,False),(-1,False)]:
  result=retained_record(source,code,old['period'],observed+timedelta(seconds=age));assert bool(result)==allowed,(code,age)
  if allowed:
   assert result['observed_at']==old['observed_at'] and result['source_sha256']==old['source_sha256']
   assert result['status']=='cached' and result['source_revalidated'] is False and result['alerts']==[]
   assert result['current']==old['current'] and result['previous']==old['previous']
  checks.append({'code':code,'synthetic_age_seconds':age,'expected_retain':allowed,'passed':True})
print(json.dumps({'mode':'synthetic boundary checks; not live source validation','source_sha256':hashlib.sha256((root/'remote/working_capital.json').read_bytes()).hexdigest(),'checks':checks,'passed':len(checks),'freshness_not_renewed':True},ensure_ascii=False,indent=2))
