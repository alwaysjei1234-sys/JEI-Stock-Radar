"""Compare a pinned pre-fix diagnostic with the current repository, offline."""
import argparse,copy,hashlib,itertools,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--output',type=Path,required=True);args=p.parse_args();root=args.repo.resolve();sys.path.insert(0,str(root))
from scripts.audit_feed_health import check
before_sha='7475d41e4fea67beb9213e18251257197b49fbe0'
source=subprocess.check_output(['git','-C',str(root),'show',before_sha+':scripts/audit_feed_health.py'],text=True)
namespace={'__name__':'pinned_prior_health_audit'};exec(compile(source,'pinned_prior_health_audit','exec'),namespace);old=namespace['check']
def base():return {'market':{'live_valid':True,'live_count':600,'close_count':1500,'live_coverage_pct':40,'partial_live':None,'live_diagnostics':{'market_open':True,'quote_refresh_window':True,'mis_stats':{'returned_messages':600,'missing_last_trade':0}}}}
rows=[]
for live,stale,readonly,no_new in itertools.product((False,True),repeat=4):
 feed=base();feed['market'].update(live_valid=live,stale=stale,historical_readonly=readonly,no_new_picks=no_new);invalid=live and(stale or readonly or no_new);prior=copy.deepcopy(feed);new=check(feed);assert bool(new)==invalid;assert feed==prior;rows.append({'kind':'flags','flags':[live,stale,readonly,no_new],'should_degrade':invalid,'old_issues':old(feed),'new_issues':new})
for total,pct,invalid in [(1500,40,False),(2000,40,True),(500,40,True),(0,40,True),(True,40,True),(1500.5,40,True),(1500,39.9,False),(1500,39.8,True)]:
 feed=base();feed['market'].update(close_count=total,live_coverage_pct=pct);new=check(feed);assert bool(new)==invalid;rows.append({'kind':'coverage','close_count':total,'coverage_pct':pct,'should_degrade':invalid,'old_issues':old(feed),'new_issues':new})
result={'schema':1,'prior_sha':before_sha,'current_sha':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'prior_source_sha256':hashlib.sha256(source.encode()).hexdigest(),'cases':rows,'case_count':len(rows),'previous_false_passes':sum(r['should_degrade']and not r['old_issues']for r in rows),'current_false_passes':sum(r['should_degrade']and not r['new_issues']for r in rows),'scope':'synthetic diagnostics only; does not validate market availability or investment returns'}
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in result.items()if k not in ['cases','prior_source_sha256']})
