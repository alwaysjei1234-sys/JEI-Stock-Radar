import json,sys
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import argparse
a=argparse.ArgumentParser();a.add_argument('--repo',type=Path,default=Path.cwd());root=a.parse_args().repo.resolve();sys.path.insert(0,str(root))
from scripts import update_system as u
p=Path(__file__).resolve().parent/'freshness-cases.json';d=json.loads(p.read_text());now=datetime.fromisoformat(d['now']).astimezone(u.TZ)
for row in d['cases']:
 with patch.object(u,'fetch_mis_channels',return_value=[row['quote']]):
  result=u.enrich_live([{'code':'2330','market':'TWSE','close':99}],now)
 row['jei_valid_trades']=result[1];assert result[1]==int(row['name']=='fresh'),row
p.write_text(json.dumps(d,ensure_ascii=False,indent=2));print('8 JEI replay cases passed: 1 fresh accepted, 7 invalid or outdated rejected')
