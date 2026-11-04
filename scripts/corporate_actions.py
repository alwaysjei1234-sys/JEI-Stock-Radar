"""Known official ex-rights/dividend flags; no guessed adjustment factors."""
import re
from datetime import date

NOTES={'除權','除息','除權息'}


def action_note(raw):
    text=re.sub(r'<[^>]+>','',str(raw or '')).replace(' ','')
    if '除權息' in text or ('除權' in text and '除息' in text):return '除權息'
    if '除權' in text:return '除權'
    if '除息' in text:return '除息'
    return None


def validated_actions(archive):
    events=archive.get('corporate_actions',{})
    if not isinstance(events,dict):raise ValueError('除權息註記格式錯誤')
    for day,rows in events.items():
        try:
            if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:raise ValueError()
        except (ValueError,TypeError):raise ValueError('除權息註記日期錯誤') from None
        if not isinstance(rows,dict):raise ValueError('除權息股票註記格式錯誤')
        for code,note in rows.items():
            if not isinstance(code,str) or not re.fullmatch(r'[0-9A-Z]{4,8}',code) or not isinstance(note,str) or note not in NOTES:
                raise ValueError('除權息股票註記無法驗證')
    return events


def actions_between(events,code,start,end):
    return [{'day':day,'note':rows[code]} for day,rows in sorted(events.items())
            if start<day<=end and code in rows]
