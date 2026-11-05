"""Replay public MIS time fields; does not fetch, mutate, or qualify trading signals."""
import json,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from scripts.update_system import recent_mis_time
bundle=json.loads(Path(sys.argv[2]).read_text());rows=[]
for message in bundle['quotes']:
 explicit=datetime.strptime(message['d']+' '+message['t'],'%Y%m%d %H:%M:%S').replace(tzinfo=ZoneInfo('Asia/Taipei'))
 epoch=datetime.fromtimestamp(int(message['tlong'])/1000,ZoneInfo('Asia/Taipei'))
 row={'code':message['c'],'explicit_taipei':explicit.isoformat(),'epoch_taipei':epoch.isoformat(),'epoch_utc':epoch.astimezone(ZoneInfo('UTC')).isoformat(),'difference_seconds':(epoch-explicit).total_seconds()}
 if message['c']!='t00':
  assert recent_mis_time(message,explicit) is True
  assert recent_mis_time(message,epoch) is False
  row['jei_rejects_one_hour_old_quote_at_epoch_time']=True
 rows.append(row)
assert [x['difference_seconds']for x in rows]==[3600,3600,0]
print(json.dumps({'source_checked_at':bundle['checked_at'],'historical_replay_only':True,'rows':rows,'external_twstock_code_executed':False},ensure_ascii=False,indent=2))
