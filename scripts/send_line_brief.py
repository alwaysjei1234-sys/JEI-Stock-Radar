#!/usr/bin/env python3
"""LINE daily research brief: default disabled; secrets and free quota required."""
import argparse
import json
import os
import re
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

def payload(report,recipient):
    lines=[report.get("title") or "JEI 市場摘要",str(report.get("date") or ""),str(report.get("note") or "")]
    for block in (report.get("blocks") or [])[:4]:
        lines.append("【"+str(block.get("title") or "")[:40]+"】")
        lines.extend(str(x)[:120] for x in (block.get("items") or [])[:2])
    lines.append("詳細內容："+str(report.get("report_url") or "https://jei-stock-radar.vercel.app/remote/brief.html"))
    lines.append("僅研究參考，非即時行情或買賣建議。")
    return {"to":recipient,"messages":[{"type":"text","text":"\n".join(lines)[:3500]}],"notificationDisabled":False}

def api_get(path,token):
    req=urllib.request.Request(BASE+path,headers={"Authorization":"Bearer "+token})
    with urllib.request.urlopen(req,timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))

def quota_ok(token,cap=55):
    # Fail closed: only the Taiwan light free plan (200 max), no paid top-ups.
    quota=api_get("/v2/bot/message/quota",token)
    consumption=api_get("/v2/bot/message/quota/consumption",token)
    maximum=quota.get("value")
    used=consumption.get("totalUsage")
    return (quota.get("type")=="limited" and isinstance(maximum,int) and 0<maximum<=200
            and isinstance(used,int) and 0<=used<min(cap,maximum))

def push(report,edition,token,recipient,receipt=None):
    receipt = receipt if receipt is not None else {}
    if not quota_ok(token):
        receipt["status"]="quota_blocked"
        return "LINE 免費方案額度未通過安全檢查，跳過推播"
    # Official retry key: avoid duplicate acceptance for the same daily edition.
    key=str(uuid.uuid5(uuid.NAMESPACE_URL,"jei-stock-radar/"+recipient+"/"+report["date"]+"/"+edition))
    body=json.dumps(payload(report,recipient),ensure_ascii=False).encode("utf-8")
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
        raise RuntimeError("LINE 發送未被接受（HTTP "+str(e.code)+"）") from None

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
