"""Extract same-date observed closing price proxies from JEI feed stock lists.

Do not treat a model target or entry_low as a closing price. This captures only
the price field present in the feed, with provenance; official close validation
is still required before a production performance claim.
"""
import argparse
import json
from datetime import date
from pathlib import Path

SECTIONS=("attack","monster","future_monster","tomorrow_monster","next","rotate","priority")

def extract_closes(feed):
    as_of=date.fromisoformat(feed["data_date"]).isoformat()
    found={}
    conflicts=[]
    for section in SECTIONS:
        rows=feed.get(section,[])
        if not isinstance(rows,list):
            continue
        for row in rows:
            if not isinstance(row,dict):
                continue
            code=str(row.get("code","")).strip()
            price=row.get("price")
            if not code or isinstance(price,bool) or not isinstance(price,(int,float)) or not (0<price<float("inf")):
                continue
            if code in found and found[code]["close"]!=price:
                conflicts.append(code)
                continue
            found.setdefault(code,{"date":as_of,"close":price,"source_section":section})
    for code in set(conflicts):
        found.pop(code,None)
    return {"schema_version":1,"data_date":as_of,
            "source":"remote/system.json.price (feed snapshot; official close not independently confirmed)",
            "conflict_codes":sorted(set(conflicts)),
            "prices":found}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feed",type=Path,default=Path("remote/system.json"))
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    data=extract_closes(json.loads(args.feed.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(f"Captured {len(data['prices'])} feed prices; {len(data['conflict_codes'])} conflicts.")

if __name__=="__main__":
    main()
