#!/usr/bin/env python3
"""Publish an allowlisted daily LINE decision, never a recipient or API body."""
import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo('Asia/Taipei')
RUN_BASE = 'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/'
STATUSES = {'accepted', 'already_accepted', 'blocked', 'quota_blocked', 'failed'}
EDITIONS = {'morning', 'close', 'morning_unavailable', 'close_unavailable'}
POLICY_CODES = {'non_weekday', 'market_closed', 'morning_window_expired', 'dispatch_window_not_open', 'brief_failed_before_send'}


def public_record(receipt, run_id, now):
    if not isinstance(receipt, dict) or not re.fullmatch(r'[1-9][0-9]{0,23}', str(run_id)):
        raise ValueError('Invalid LINE evidence')
    status, edition = receipt.get('status'), receipt.get('edition')
    if status not in STATUSES or edition not in EDITIONS:
        raise ValueError('Invalid LINE decision')
    try:
        day = date.fromisoformat(receipt['date'])
        checked = datetime.fromisoformat(receipt['checked_at'])
        if checked.tzinfo is None or now.tzinfo is None:
            raise ValueError('Timezone required')
        checked = checked.astimezone(TAIPEI)
        if checked.date() != day or checked > now + timedelta(seconds=120):
            raise ValueError('Invalid evidence date')
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError('Invalid evidence date') from error
    http = receipt.get('http_status')
    if status in {'accepted', 'already_accepted'} and (type(http) is not int or http != (200 if status == 'accepted' else 409)):
        raise ValueError('Acceptance requires the matching HTTP result')
    result = {'date': day.isoformat(), 'edition': edition,
              'checked_at': checked.isoformat(timespec='seconds'), 'status': status,
              'api_accepted': status in {'accepted', 'already_accepted'},
              'delivery_confirmed': False, 'evidence_url': RUN_BASE + str(run_id)}
    if type(http) is int and 100 <= http <= 599:
        result['http_status'] = http
    attempts = receipt.get('attempts')
    if type(attempts) is int and 1 <= attempts <= 3:
        result['attempts'] = attempts
    # Intentionally exclude request_id, recipient, body, reason, exception text,
    # environment and credentials, including arbitrary fields in older records.
    return result


def public_policy_record(receipt, run_id, now):
    if (not isinstance(receipt,dict) or receipt.get('record_kind') != 'policy_check'
            or receipt.get('status') != 'policy_skipped' or receipt.get('policy_code') not in POLICY_CODES
            or receipt.get('edition') not in {'morning','close'}):
        raise ValueError('Invalid schedule policy evidence')
    row=public_record({key:receipt.get(key) for key in ('date','edition','checked_at')}
                      | {'status':'blocked'},run_id,now)
    row.update(record_kind='policy_check',status='policy_skipped',policy_code=receipt['policy_code'])
    return row


def clean_policy_checks(document, now):
    cleaned={}
    checks=document.get('policy_checks') if isinstance(document,dict) else None
    for slot in ('morning','close'):
        row=checks.get(slot) if isinstance(checks,dict) else None
        if not isinstance(row,dict):continue
        url=row.get('evidence_url')
        if not isinstance(url,str) or not url.startswith(RUN_BASE):continue
        try:clean=public_policy_record(row,url[len(RUN_BASE):],now)
        except (ValueError,TypeError):continue
        if clean['edition']==slot:cleaned[slot]=clean
    return cleaned


def merge_status(document, receipt, run_id, now=None):
    now = now or datetime.now(TAIPEI)
    incoming = public_record(receipt, run_id, now)
    records = {}
    acceptances = []
    prior = document.get('editions') if isinstance(document, dict) else None
    if isinstance(prior, dict):
        for slot in ('morning', 'close'):
            row = prior.get(slot)
            if not isinstance(row, dict):
                continue
            url = row.get('evidence_url')
            if not isinstance(url, str) or not url.startswith(RUN_BASE):
                continue
            try:
                clean = public_record(row, url[len(RUN_BASE):], now)
            except (ValueError, TypeError):
                continue
            if clean['edition'].split('_', 1)[0] == slot:
                records[slot] = clean
                if clean['api_accepted']:
                    acceptances.append(clean)
                nested = row.get('accepted_attempt')
                if isinstance(nested, dict):
                    nested_url = nested.get('evidence_url')
                    if isinstance(nested_url, str) and nested_url.startswith(RUN_BASE):
                        try:
                            accepted = public_record(nested, nested_url[len(RUN_BASE):], now)
                        except (ValueError, TypeError):
                            continue
                        if (accepted['api_accepted'] and accepted['date'] == clean['date']
                                and accepted['edition'] == clean['edition']
                                and accepted['checked_at'] <= clean['checked_at']):
                            acceptances.append(accepted)
    slot = incoming['edition'].split('_', 1)[0]
    previous = records.get(slot)
    if previous is None or incoming['checked_at'] >= previous['checked_at']:
        records[slot] = incoming
    if incoming['api_accepted']:
        acceptances.append(incoming)
    # A failed backup is a new decision, not a revocation of prior acceptance.
    # Keep only the earliest validated acceptance for the same date and exact
    # report edition; unavailable notices must not stand in for market reports.
    for row in records.values():
        matching = [accepted for accepted in acceptances
                    if accepted['date'] == row['date'] and accepted['edition'] == row['edition']
                    and accepted['checked_at'] <= row['checked_at']]
        if matching:
            row['accepted_attempt'] = dict(min(matching, key=lambda item: item['checked_at']))
    checks=clean_policy_checks(document,now)
    result={'schema':1,'updated_at':max(x['checked_at'] for x in [*records.values(),*checks.values()]),
            'editions':records}
    if checks:result['policy_checks']=checks
    return result


def merge_policy_status(document, receipt, run_id, now=None):
    now=now or datetime.now(TAIPEI)
    incoming=public_policy_record(receipt,run_id,now)
    result={'schema':1,'editions':{},'policy_checks':clean_policy_checks(document,now)}
    # Reuse the acceptance sanitizer, including same-day accepted_attempt
    # preservation. A policy decision must never replace an API attempt.
    prior=document.get('editions') if isinstance(document,dict) else None
    for slot in ('morning','close'):
        row=prior.get(slot) if isinstance(prior,dict) else None
        if not isinstance(row,dict):continue
        if str(row.get('edition','')).split('_',1)[0]!=slot:continue
        url=row.get('evidence_url')
        if not isinstance(url,str) or not url.startswith(RUN_BASE):continue
        try:result=merge_status(document,row,url[len(RUN_BASE):],now)
        except (ValueError,TypeError):continue
        break
    checks=result.setdefault('policy_checks',{})
    previous=checks.get(incoming['edition'])
    repeated=previous is not None and previous['date']==incoming['date'] and previous['policy_code']==incoming['policy_code']
    if previous is None or (not repeated and incoming['checked_at']>=previous['checked_at']):
        checks[incoming['edition']]=incoming
    result['updated_at']=max(x['checked_at'] for x in [*result['editions'].values(),*checks.values()])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', default='remote/line_status.json')
    args = parser.parse_args()
    output = Path(args.output)
    try:
        prior = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
        receipt = json.loads(Path(args.receipt).read_text(encoding='utf-8'))
        merge=merge_policy_status if receipt.get('record_kind')=='policy_check' else merge_status
        result = merge(prior, receipt, args.run_id)
    except (OSError, ValueError, TypeError, AttributeError):
        raise SystemExit('LINE status evidence unavailable or invalid; nothing published') from None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print('Public LINE decision saved; phone delivery remains unconfirmed')


if __name__ == '__main__':
    main()
