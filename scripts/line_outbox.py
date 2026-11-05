"""Freeze already-public brief text before dispatch; never persist a recipient/key/token."""
import argparse
import copy
import json
from datetime import datetime
from pathlib import Path

from scripts.send_line_brief import TAIPEI, can_send, payload, select_dispatch, text_units

EDITIONS = {'morning', 'close', 'morning_unavailable', 'close_unavailable'}


def validate_payload(body):
    if not isinstance(body, dict) or set(body) != {'messages', 'notificationDisabled'}:
        raise ValueError('Invalid public LINE payload')
    messages = body['messages']
    if (body['notificationDisabled'] is not False or not isinstance(messages, list) or len(messages) != 1
            or not isinstance(messages[0], dict) or set(messages[0]) != {'type', 'text'}
            or messages[0]['type'] != 'text' or not isinstance(messages[0]['text'], str)
            or not 0 < text_units(messages[0]['text']) <= 3500):
        raise ValueError('Invalid public LINE message')
    return copy.deepcopy(body)


def read_document(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(doc, dict) or set(doc) != {'schema', 'records'}
            or type(doc['schema']) is not int or doc['schema'] != 1 or not isinstance(doc['records'], dict)):
        raise ValueError('Invalid LINE outbox schema')
    for key, record in doc['records'].items():
        if (not isinstance(record, dict) or set(record) != {'date', 'edition', 'payload'}
                or not isinstance(key, str) or not isinstance(record['date'], str)
                or not isinstance(record['edition'], str) or record['edition'] not in EDITIONS or key != record['date']+'/'+record['edition']):
            raise ValueError('Invalid LINE outbox record')
        datetime.strptime(record['date'], '%Y-%m-%d')
        validate_payload(record['payload'])
    return doc


def load(path, day, edition):
    doc = read_document(path)
    record = doc['records'].get(day+'/'+edition)
    if record is None:
        raise ValueError('LINE message was not frozen before publication')
    return validate_payload(record['payload'])


def freeze(document, edition, now, path, prior_status):
    report, selected = select_dispatch(document, edition, now)
    # Reuse the established date/readiness gate; dummy values never leave this
    # process and no credential or recipient is needed to freeze public content.
    if not can_send(report, selected, now, 'true', 'validation-only', 'U'+'0'*32)[0]:
        raise ValueError('Current report is not verified for dispatch')
    path = Path(path)
    outbox = read_document(path) if path.exists() else {'schema': 1, 'records': {}}
    key = report['date']+'/'+selected
    if key in outbox['records']:
        return selected
    # Migration guard: an earlier accepted legacy report has no saved body.
    # Never manufacture a new body for its already-used daily retry bucket.
    rows = prior_status.get('editions', {}) if isinstance(prior_status, dict) else {}
    for row in rows.values() if isinstance(rows, dict) else []:
        if not isinstance(row, dict): continue
        for old in [row, row.get('accepted_attempt')]:
            if (isinstance(old, dict) and old.get('date') == report['date']
                    and old.get('edition') == selected and old.get('api_accepted') is True):
                raise ValueError('Accepted legacy edition has no frozen body; refusing reconstruction')
    body = payload(report, '')
    body.pop('to')
    outbox['records'][key] = {'date': report['date'], 'edition': selected, 'payload': validate_payload(body)}
    # Keep seven dates; records for today's separate notice/report buckets stay.
    days = sorted({row['date'] for row in outbox['records'].values()})[-7:]
    outbox['records'] = {k: v for k, v in outbox['records'].items() if v['date'] in days}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(outbox, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--edition', required=True, choices=['morning', 'close'])
    parser.add_argument('--brief', default='remote/brief.json')
    parser.add_argument('--outbox', default='remote/line_outbox.json')
    parser.add_argument('--status', default='remote/line_status.json')
    args = parser.parse_args()
    prior = json.loads(Path(args.status).read_text(encoding='utf-8')) if Path(args.status).exists() else {}
    selected = freeze(json.loads(Path(args.brief).read_text(encoding='utf-8')), args.edition,
                      datetime.now(TAIPEI), args.outbox, prior)
    print('Public LINE message frozen before publication: '+selected)


if __name__ == '__main__':
    main()
