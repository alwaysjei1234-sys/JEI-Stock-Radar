"""Keep routine builds silent; allow an expiring, explicitly named close verification."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

TAIPEI=ZoneInfo('Asia/Taipei')
VERIFY_MESSAGE='verify(line): dispatch 2026-11-05 close with immutable outbox'
VERIFY_DAY='2026-11-05'
MORNING={'55 0 * * 1-5','10 1 * * 1-5','25 1 * * 1-5'}
CLOSE={'10 10 * * 1-5','40 10 * * 1-5','10 11 * * 1-5'}


def select_policy(event,schedule,selected,manual_send,head_message,now):
    if now.tzinfo is None:
        raise ValueError('Dispatch policy needs a timezone')
    selected=selected or 'close'
    if selected not in {'morning','close'}:
        raise ValueError('Invalid brief edition')
    local=now.astimezone(TAIPEI)
    if event=='schedule':
        if schedule in MORNING:return 'morning',True
        if schedule in CLOSE:return 'close',True
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
