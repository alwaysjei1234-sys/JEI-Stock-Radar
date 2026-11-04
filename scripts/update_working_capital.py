#!/usr/bin/env python3
"""Narrow official iXBRL working-capital checks; public tickers, no trading signals.

Fetch only the quarterly period already identified in the official research
feed. Observed time is NOT a historical publication date or backtest input.
"""
import calendar
import hashlib
import io
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
BASE='https://mopsov.twse.com.tw/server-java/FileDownLoad'
LIMIT=4_000_000
VERSION='working-capital-yoy-v1'
XBRLI='http://www.xbrl.org/2003/instance'
IX='http://www.xbrl.org/2013/inlineXBRL'
FIELDS={'inventory':('ifrs-full','Inventories'),
        'receivables':('tifrs-bsci-ci','AccountsReceivableNet'),
        'revenue_ytd':('ifrs-full','Revenue')}


def quarter_end(year,quarter):
    month=quarter*3
    return date(year,month,calendar.monthrange(year,month)[1]).isoformat()


def parse_filing(content,code,year,quarter,today):
    if (not re.fullmatch(r'\d{4}',code) or quarter not in (1,2,3,4)
            or not 2013<=year<=today.year or quarter_end(year,quarter)>today.isoformat()):
        raise ValueError('Invalid company or reporting period')
    if len(content)>LIMIT or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('Unsupported XML declarations or size')
    namespaces={}
    for _,(prefix,uri) in ET.iterparse(io.BytesIO(content),events=['start-ns']):
        if prefix in namespaces and namespaces[prefix]!=uri:
            raise ValueError('Ambiguous namespace')
        namespaces[prefix]=uri
    root=ET.fromstring(content)
    allowed={
        'ifrs-full':r'https?://xbrl\.ifrs\.org/taxonomy/\d{4}-\d{2}-\d{2}/ifrs-full',
        'tifrs-bsci-ci':r'http://www\.xbrl\.org/tifrs/bsci/ci/\d{4}-\d{2}-\d{2}'}
    concepts={}
    for field,(prefix,local) in FIELDS.items():
        for actual,uri in namespaces.items():
            if re.fullmatch(allowed[prefix],uri):concepts[actual+':'+local]=field
    units=set()
    for unit in root.iter('{'+XBRLI+'}unit'):
        children=list(unit)
        if len(children)==1 and children[0].tag=='{'+XBRLI+'}measure':
            measure=(children[0].text or '').strip().split(':')
            if (len(measure)==2 and measure[1]=='TWD'
                    and namespaces.get(measure[0])=='http://www.xbrl.org/2003/iso4217'):
                units.add(unit.get('id'))
    contexts={}
    for ctx in root.iter('{'+XBRLI+'}context'):
        # Reject segmented/subsidiary/dimensional values, even if they share dates.
        tags=[e.tag.rsplit('}',1)[-1] for e in ctx.iter()]
        ids=[(e.text or '').strip() for e in ctx.iter('{'+XBRLI+'}identifier')]
        if ids!=[code] or any(t in tags for t in ('scenario','segment','explicitMember','typedMember')):
            continue
        values={e.tag.rsplit('}',1)[-1]:(e.text or '').strip() for e in ctx.iter()}
        instant=values.get('instant')
        contexts[ctx.get('id')]=(instant or values.get('endDate'),None if instant else values.get('startDate'))
    ends=[quarter_end(year,quarter),quarter_end(year-1,quarter)]
    buckets={end:{} for end in ends}
    for fact in root.iter('{'+IX+'}nonFraction'):
        field=concepts.get(fact.get('name'))
        period=contexts.get(fact.get('contextRef'))
        if not field or not period or period[0] not in buckets or fact.get('unitRef') not in units:
            continue
        end,start=period
        if field=='revenue_ytd':
            if start!=end[:4]+'-01-01':continue
        elif start is not None:continue
        if (fact.get('{http://www.w3.org/2001/XMLSchema-instance}nil') in ('true','1')
                or fact.get('continuedAt') or fact.get('sign') not in (None,'-')):
            continue
        fmt=fact.get('format','').split(':')
        if (len(fmt)!=2 or fmt[1] not in ('numdotdecimal','num-dot-decimal')
                or not namespaces.get(fmt[0],'').startswith('http://www.xbrl.org/inlineXBRL/transformation/')):
            continue
        text=''.join(fact.itertext()).strip().replace(',','')
        try:
            scale=int(fact.get('scale','0'))
            if not -9<=scale<=9 or not re.fullmatch(r'\d+(?:\.\d+)?',text):continue
            value=Decimal(text)*(Decimal(10)**scale)*(-1 if fact.get('sign')=='-' else 1)
            if not value.is_finite() or value<0:continue
            number=float(value)
            if not math.isfinite(number):continue
        except (ValueError,InvalidOperation,OverflowError):continue
        existing=buckets[end].get(field)
        if existing is not None and existing!=number:
            raise ValueError('Conflicting duplicate facts')
        buckets[end][field]=number
    current,previous=(buckets[end] for end in ends)
    if not any(current.values()):raise ValueError('No matching consolidated facts')
    raw_growth={key:100*(current[key]/previous[key]-1)
            if key in current and previous.get(key,0)>0 else None for key in FIELDS}
    growth={key:round(value,3) if value is not None else None for key,value in raw_growth.items()}
    alerts=[]
    for key in ('inventory','receivables'):
        if (raw_growth[key] is not None and raw_growth['revenue_ytd'] is not None
                and raw_growth[key]>0 and raw_growth[key]-raw_growth['revenue_ytd']>=20-1e-9):
            alerts.append(key+'_growth_exceeds_revenue')
    complete=all(k in current and k in previous and growth[k] is not None for k in FIELDS)
    return {'code':code,'period':f'{year}-Q{quarter}','period_end':ends[0],
            'comparison_period_end':ends[1],'unit':'TWD','revenue_basis':'year_to_date',
            'current':current,'previous':previous,'yoy_pct':growth,'alerts':alerts,
            'status':'comparable' if complete else 'partial',
            'rule_version':VERSION,'growth_gap_threshold_pp':20,
            'source_sha256':hashlib.sha256(content).hexdigest(),
            'not_for_historical_backtest':True}


def fetch_record(code,period,today):
    match=re.fullmatch(r'(20\d{2})-Q([1-4])',period or '')
    if not match:raise ValueError('Missing official period')
    year,quarter=map(int,match.groups())
    # All URL parameters are constrained; TLS verification remains enabled.
    url=f'{BASE}?functionName=t164sb01&step=9&co_id={code}&year={year}&season={quarter}&report_id=C'
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 JEI-public-research',
        'Referer':'https://mopsov.twse.com.tw/mops/web/t203sb01'})
    with urllib.request.urlopen(request,timeout=20) as response:content=response.read(LIMIT+1)
    return {**parse_filing(content,code,year,quarter,today),'source_url':url}


def build(system,research,now,fetch=fetch_record):
    holdings=system.get('holdings',{})
    markets=research.get('markets',{})
    jobs=[]
    for code in sorted(holdings if isinstance(holdings,dict) else {})[:50]:
        if not re.fullmatch(r'\d{4}',code):continue
        record=markets.get('listed',{}).get(code) or markets.get('otc',{}).get(code) or {}
        period=(record.get('financials') or {}).get('period')
        if period:jobs.append((code,period))
    def one(job):
        code,period=job
        try:return code,{**fetch(code,period,now.date()),'observed_at':now.isoformat(timespec='seconds')}
        except Exception as error:
            # No response bodies, local paths, user positions or exception text.
            return code,{'code':code,'period':period,'status':'unavailable',
                         'error_type':type(error).__name__,'observed_at':now.isoformat(timespec='seconds')}
    with ThreadPoolExecutor(max_workers=2) as pool:records=dict(pool.map(one,jobs))
    return {'schema':1,'generated_at':now.isoformat(timespec='seconds'),
            'rule_version':VERSION,'source':'MOPS consolidated iXBRL',
            'notes':'依官方研究快照季度取報表，不保證最新申報。營收為同期間累計，金額為新台幣元；20百分點差距僅查核提醒，各產業營運差異可能造成誤警，不能直接判定滯銷、壞帳或交易方向。observed_at非公告時間，不供歷史回測。',
            'records':records}


def main():
    system=json.loads((ROOT/'remote/system.json').read_text())
    research=json.loads((ROOT/'remote/free_research.json').read_text())
    result=build(system,research,datetime.now(timezone.utc))
    output=ROOT/'remote/working_capital.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'requested':len(result['records']),
        'available':sum(r['status']!='unavailable' for r in result['records'].values())}))


if __name__=='__main__':main()
