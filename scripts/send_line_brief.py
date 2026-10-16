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

def push(report,edition,token,recipient):
    if not quota_ok(token):
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
            return "LINE Messaging API 已接受推播請求"
    except urllib.error.HTTPError as e:
        if e.code==409: return "LINE 已接受相同日期報告，不重複發送"
        raise RuntimeError("LINE 發送未被接受（HTTP "+str(e.code)+"）") from None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--edition",choices=["morning","close"],required=True)
    args=p.parse_args()
    now=datetime.now(TAIPEI)
    path=ROOT/"remote/brief.json"
    report=json.loads(path.read_text(encoding="utf-8")).get(args.edition) or {}
    token=os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN","")
    recipient=os.getenv("JEI_LINE_USER_ID","")
    ok,msg=can_send(report,args.edition,now,os.getenv("JEI_LINE_ENABLED",""),token,recipient)
    if not ok:
        print(msg)
        return
    print(push(report,args.edition,token,recipient))

if __name__=="__main__": main()
