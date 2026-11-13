"""Keep routine builds silent; allow an expiring, explicitly named close verification."""
import os
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

TAIPEI=ZoneInfo('Asia/Taipei')
VERIFY_MESSAGE='verify(line): dispatch 2026-11-05 close with immutable outbox'
VERIFY_DAY='2026-11-05'
# Earliest local start for each configured UTC cron. A delayed schedule event
# does not carry a trustworthy intended trading date, so fail closed when its
# wall-clock slot has not started today (especially after midnight).
MORNING={'55 0 * * 1-5':8*60+55,'10 1 * * 1-5':9*60+10,
         '25 1 * * 1-5':9*60+25}
CLOSE={'10 10 * * 1-5':18*60+10,'40 10 * * 1-5':18*60+40,
       '10 11 * * 1-5':19*60+10}


def select_policy(event,schedule,selected,manual_send,head_message,now):
    if now.tzinfo is None:
        raise ValueError('Dispatch policy needs a timezone')
    selected=selected or 'close'
    if selected not in {'morning','close'}:
        raise ValueError('Invalid brief edition')
    local=now.astimezone(TAIPEI)
    if event=='schedule':
        minute=local.hour*60+local.minute
        weekday=local.weekday()<5
        if schedule in MORNING:
            return 'morning',weekday and MORNING[schedule]<=minute<13*60+30
        if schedule in CLOSE:
            return 'close',weekday and minute>=CLOSE[schedule]
        return 'close',False
    if (event=='push' and head_message==VERIFY_MESSAGE and local.date().isoformat()==VERIFY_DAY
            and local.hour*60+local.minute>=810):
        return 'close',True
    return selected,event=='workflow_dispatch' and manual_send=='true'


def skipped_receipt(event, schedule, now):
    """Only actual send schedules get diagnostics; routine builds stay silent."""
    if event != 'schedule' or schedule not in {*MORNING, *CLOSE}:
        return None
    edition, send = select_policy(event, schedule, 'close', 'false', '', now)
    if send:
        return None
    local = now.astimezone(TAIPEI)
    code = ('non_weekday' if local.weekday() >= 5 else
            'morning_window_expired' if schedule in MORNING and local.hour*60+local.minute >= 810
            else 'dispatch_window_not_open')
    return policy_receipt(edition, local, code)


def policy_receipt(edition, local, code):
    return {'record_kind':'policy_check','date':local.date().isoformat(),
            'edition':edition,'checked_at':local.isoformat(timespec='seconds'),
            'status':'policy_skipped','policy_code':code}


def record_pre_send_failure(edition, path, now=None):
    if edition not in {'morning', 'close'}:
        raise ValueError('Invalid brief edition')
    local = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    receipt = policy_receipt(edition, local, 'brief_failed_before_send')
    # Never overwrite evidence from another stage.
    try:
        with Path(path).open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False)+'\n')
    except FileExistsError:
        pass


def main():
    now=datetime.now(TAIPEI)
    edition,send=select_policy(os.getenv('EVENT',''),os.getenv('SCHEDULE',''),
        os.getenv('SELECTED',''),os.getenv('MANUAL_SEND','false'),
        os.getenv('COMMIT_MESSAGE',''),now)
    print('name='+edition)
    print('send='+str(send).lower())
    receipt=skipped_receipt(os.getenv('EVENT',''),os.getenv('SCHEDULE',''),now)
    path=os.getenv('LINE_POLICY_RECEIPT_PATH','')
    if receipt and path:
        Path(path).write_text(json.dumps(receipt,ensure_ascii=False)+'\n',encoding='utf-8')
    if path:
        print('policy_recorded='+str(bool(receipt)).lower())


if __name__=='__main__':main()
