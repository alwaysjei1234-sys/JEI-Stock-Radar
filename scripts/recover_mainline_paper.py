"""Recover missing paper observations from contemporaneous, unchanged-rule main blobs.

Historical reconstruction is research only. Missing days, revised prices, changed
rules or late publications stop the whole recovery without modifying the caller.
"""
import copy
import hashlib
import json
import subprocess
from datetime import datetime
from scripts.paper_provenance import ROOT, RULE_FILES
from scripts.recover_pick_history import git_snapshots
from scripts.update_pick_validation import close_verified, TZ
from scripts.update_paper_performance import advance


def read_source(source):
    sha = source['sha']
    def blob(path):
        return subprocess.check_output(['git', 'show', sha+':'+path], cwd=ROOT)
    if any(blob(path) != (ROOT/path).read_bytes() for path in RULE_FILES):
        raise ValueError('Historical strategy rules differ; cannot reconstruct '+sha)
    return json.loads(blob('remote/daily_prices.json'))


def recover(state, current_archive, sources, now, reader=read_source):
    if now.tzinfo is None:
        raise ValueError('Recovery requires a timezone')
    local = now.astimezone(TZ)
    last = state.get('last_processed_day')
    if not last:
        raise ValueError('Recovery requires an existing paper ledger')
    required = sorted(d for d in current_archive['days']
                      if last < d <= local.date().isoformat())
    if not required:
        return copy.deepcopy(state), []
    chosen = {}
    for source in sources:
        feed = source['feed']; day = feed.get('data_date')
        if day not in required or day in chosen or not close_verified(feed,current_archive,day):
            continue
        committed = datetime.fromisoformat(source['committed_at']).astimezone(TZ)
        stamp = datetime.strptime(feed['updated_at'],'%Y-%m-%d %H:%M').replace(tzinfo=TZ)
        if committed.date().isoformat() != day or not stamp <= committed <= local:
            continue
        # Do not skip an early publication in favour of a better later result.
        original_archive = reader(source)
        if (not close_verified(feed,original_archive,day) or
                original_archive['days'][day] != current_archive['days'][day]):
            raise ValueError('Historical official prices conflict: '+day)
        chosen[day] = source, original_archive
    missing = [day for day in required if day not in chosen]
    if missing:
        raise ValueError('Missing contemporaneous paper sessions: '+', '.join(missing))
    result = copy.deepcopy(state); proof = []
    for day in required:
        source, original_archive = chosen[day]
        before = len(result['signals'])
        advance(source['feed'],original_archive,result,day)
        for signal in result['signals'][before:]:
            signal['provenance']['reconstructed'] = True
        proof.append({'day':day,'source_commit':source['sha'],
                      'source_blob':source['blob'],'source_committed_at':source['committed_at'],
                      'recovered_at':local.isoformat(timespec='seconds'),
                      'signals_added':len(result['signals'])-before,'qualified_oos':False,
                      'official_prices_sha256':hashlib.sha256(json.dumps(
                          original_archive['days'][day],sort_keys=True).encode()).hexdigest()})
    result.setdefault('mainline_recovery',[]).extend(proof)
    return result, proof


def recover_checkout(state, root=ROOT):
    archive = json.loads((root/'remote/daily_prices.json').read_text())
    return recover(state,archive,git_snapshots('HEAD',state['last_processed_day']),datetime.now(TZ))
