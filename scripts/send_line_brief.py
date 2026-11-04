#!/usr/bin/env python3
"""LINE daily research brief: default disabled; secrets and free quota required."""
import argparse
import json
import os
import re
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TAIPEI=ZoneInfo("Asia/Taipei")
BASE="https://api.line.me"
PUSH=BASE+"/v2/bot/message/push"

def can_send(report,edition,now,enabled,token,recipient):
    if str(enabled).lower()!="true": return False,"LINE 尚未明確啟用"
    if not token or not re.fullmatch(r"U[0-9a-f]{32}",recipient or ""):
        return False,"LINE 憑證或收件者尚未設定"
    if report.get("date")!=now.date().isoformat() or report.get("edition")!=edition:
        return False,"LINE 報告日期或版本不符"
    if report.get("status")!="ready":
        return False,"LINE 當次報告未通過行情驗證"
    return True,"ready"

def text_units(text):
    """LINE counts UTF-16 units; an ordinary Unicode emoji consumes two."""
    return sum(2 if ord(char)>0xffff else 1 for char in text)

def clip_units(value,limit):
    output=[];used=0
    for char in str(value):
        width=2 if ord(char)>0xffff else 1
        if used+width>limit:break
        output.append(char);used+=width
    return "".join(output)

def payload(report,recipient):
    lines=[clip_units(report.get("title") or "JEI 市場摘要",120),
           clip_units(report.get("date") or "",20),clip_units(report.get("note") or "",400)]
    default_url="https://jei-stock-radar.vercel.app/remote/brief.html"
    url=report.get("report_url")
    if not isinstance(url,str) or not url.startswith("https://") or text_units(url)>300:url=default_url
    footer=["詳細內容："+url,"僅研究參考，非即時行情或買賣建議。"]
    blocks=report.get("blocks")
    blocks=[b for b in blocks[:64] if isinstance(b,dict)] if isinstance(blocks,list) else []
    def priority(block):
        title=str(block.get("title") or "")
        if "風控" in title or title in ("大盤風險","未發布原因","資料尚未就緒"):return 0
        if "主攻候選" in title:return 1
        if block.get("kind")=="paper_performance" or title=="四策略模擬復盤":return 2
        return 3
    # Global blocks used to displace candidates beyond the first four slots.
    # Protect risk, picks and paper results before spending the remaining space.
    for block in sorted(blocks,key=priority)[:8]:
        title=str(block.get("title") or "")
        items=block.get("items")
        if not isinstance(items,list):continue
        is_paper=block.get("kind")=="paper_performance" or title=="四策略模擬復盤"
        limit=(8 if is_paper or title.startswith("跨市場風險指標") else
               3 if title.startswith("全球市場｜美股核心指數") else 2)
        header="【"+clip_units(title,40)+"】"
        kept=[]
        for item in items[:limit]:
            text=clip_units(item,180)
            if text_units("\n".join(lines+[header]+kept+[text]+footer))>3500:break
            kept.append(text)
        if kept:lines.extend([header,*kept])
    # Reserve the complete link and disclaimer instead of slicing them off.
    return {"to":recipient,"messages":[{"type":"text","text":"\n".join(lines+footer)}],"notificationDisabled":False}

def api_get(path,token):
    """Retry only transient read failures; never bypass a missing quota check."""
    req=urllib.request.Request(BASE+path,headers={"Authorization":"Bearer "+token})
    for attempt in range(1,4):
        try:
            with urllib.request.urlopen(req,timeout=12) as r:
                if r.status!=200:
                    raise RuntimeError("LINE quota unexpected response")
                document=json.loads(r.read().decode("utf-8"))
                if not isinstance(document,dict):
                    raise ValueError("LINE quota invalid response")
                return document
        except urllib.error.HTTPError as error:
            if not 500<=error.code<600 or attempt==3:
                raise RuntimeError("LINE quota HTTP "+str(error.code)) from None
        except OSError:
            if attempt==3:
                raise RuntimeError("LINE quota network retries exhausted") from None
        time.sleep(2**(attempt-1))

def quota_ok(token,cap=55):
    # Fail closed: only the Taiwan light free plan (200 max), no paid top-ups.
    quota=api_get("/v2/bot/message/quota",token)
    consumption=api_get("/v2/bot/message/quota/consumption",token)
    maximum=quota.get("value")
    used=consumption.get("totalUsage")
    return (quota.get("type")=="limited" and type(maximum) is int and 0<maximum<=200
            and type(used) is int and 0<=used<min(cap,maximum))

def push(report,edition,token,recipient,receipt=None):
    receipt = receipt if receipt is not None else {}
    receipt["stage"]="quota"
    if not quota_ok(token):
        receipt["status"]="quota_blocked"
        return "LINE 免費方案額度未通過安全檢查，跳過推播"
    receipt["stage"]="push"
    # Official retry key: avoid duplicate acceptance for the same daily edition.
    key=str(uuid.uuid5(uuid.NAMESPACE_URL,"jei-stock-radar/"+recipient+"/"+report["date"]+"/"+edition))
    body=json.dumps(payload(report,recipient),ensure_ascii=False).encode("utf-8")
    # Freeze content and recipient before retrying: a timeout may already have
    # been accepted upstream. Same key/body prevents a duplicate acceptance.
    for attempt in range(1,4):
        receipt["attempts"]=attempt
        receipt.pop("http_status",None)
        req=urllib.request.Request(PUSH,data=body,method="POST",headers={
            "Authorization":"Bearer "+token,"Content-Type":"application/json",
            "X-Line-Retry-Key":key,
        })
        try:
            with urllib.request.urlopen(req,timeout=15) as r:
                if r.status!=200: raise RuntimeError("LINE unexpected response")
                receipt.update(status="accepted",http_status=200,request_id=r.headers.get("x-line-request-id"))
                return "LINE Messaging API 已接受推播請求"
        except urllib.error.HTTPError as e:
            receipt["http_status"]=e.code
            if e.code==409 and e.headers.get("x-line-accepted-request-id"):
                receipt.update(status="already_accepted",request_id=e.headers.get("x-line-accepted-request-id"))
                return "LINE 已接受相同日期報告，不重複發送"
            receipt["status"]="failed"
            if not 500<=e.code<600 or attempt==3:
                raise RuntimeError("LINE 發送未被接受（HTTP "+str(e.code)+"）") from None
        except OSError:
            receipt["status"]="failed"
            if attempt==3:
                raise RuntimeError("LINE 網路重試未確認接受") from None
        time.sleep(2**(attempt-1))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--edition",choices=["morning","close"],required=True)
    p.add_argument("--result-path",help="Write a credential-free API acceptance receipt")
    args=p.parse_args()
    now=datetime.now(TAIPEI)
    receipt={"date":now.date().isoformat(),"edition":args.edition,
             "checked_at":now.isoformat(timespec="seconds"),"status":"failed",
             "delivery_confirmed":False}
    try:
        document=json.loads((ROOT/"remote/brief.json").read_text(encoding="utf-8"))
        report,edition=select_dispatch(document,args.edition,now)
        receipt["edition"]=edition
        token=os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN","")
        recipient=os.getenv("JEI_LINE_USER_ID","")
        ok,msg=can_send(report,edition,now,os.getenv("JEI_LINE_ENABLED",""),token,recipient)
        if not ok:
            receipt.update(status="blocked",reason=msg)
            raise SystemExit("未發送："+msg)
        result=push(report,edition,token,recipient,receipt=receipt)
        print(result)
        if receipt["status"] not in ("accepted","already_accepted"):
            raise SystemExit("未確認發送："+result)
    except (OSError, ValueError, RuntimeError) as error:
        # Do not serialize exception text, headers, payloads or environment secrets.
        receipt["error_type"]=type(error).__name__
        raise SystemExit("LINE 發送失敗；請查看推播結果紀錄（"+type(error).__name__+"）") from None
    finally:
        if args.result_path:
            output=Path(args.result_path)
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def select_dispatch(document,edition,now):
    """Send a current failure notice instead of silently reading an older brief.

    A notice contains no prices, scores or picks. It has a separate retry bucket
    so it cannot suppress the verified brief once data recovers.
    """
    check=(document.get("checks") or {}).get(edition) or {}
    if check.get("date")==now.date().isoformat() and check.get("status")=="pending":
        notice_edition=edition+"_unavailable"
        return {
            "date":check["date"],"edition":notice_edition,"status":"ready",
            "title":"JEI 早報資料異常通知" if edition=="morning" else "JEI 盤後資料異常通知",
            "note":"本次市場報告未通過驗證，尚未發布；這是系統狀態通知。",
            "blocks":[{"title":"未發布原因","items":[str(check.get("note") or "資料尚未就緒")[:180],
                "暫停提供本次行情、評分與選股；舊報告不代表今天行情。"]}],
            "report_url":"https://jei-stock-radar.vercel.app/remote/brief.html",
        },notice_edition
    return document.get(edition) or {},edition

if __name__=="__main__": main()
