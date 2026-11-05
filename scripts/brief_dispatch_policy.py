"""Keep routine builds silent; allow an expiring, explicitly named close verification."""
import os
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


def main():
    edition,send=select_policy(os.getenv('EVENT',''),os.getenv('SCHEDULE',''),
        os.getenv('SELECTED',''),os.getenv('MANUAL_SEND','false'),
        os.getenv('COMMIT_MESSAGE',''),datetime.now(TAIPEI))
    print('name='+edition)
    print('send='+str(send).lower())


if __name__=='__main__':main()
