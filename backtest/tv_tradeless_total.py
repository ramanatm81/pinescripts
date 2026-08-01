"""Total non-session tradeless time across the OOS (from real TV export).
Accounts for the full timeline: in-trade vs idle, and splits idle into
session-block, weekend, and OTHER (S/R zone, VWAP, dead-zone, drought, no-signal).
"""
import csv, os
from datetime import datetime, timedelta
from collections import defaultdict

PATH=os.path.expanduser("~/Downloads/input.csv")
rows=list(csv.DictReader(open(PATH,encoding="utf-8-sig")))
bn=defaultdict(dict)
for r in rows:
    num=r["Trade number"].strip(); typ=r["Type"].strip()
    dt=datetime.strptime(r["Date and time"].strip(),"%Y-%m-%d %H:%M")
    if typ.startswith("Entry"): bn[num]["entry"]=dt
    else: bn[num]["exit"]=dt
tr=[]
for num,d in bn.items():
    if "entry" in d and "exit" in d:
        tr.append(dict(num=int(num),entry=d["entry"],exit=d["exit"]))
tr.sort(key=lambda t:t["num"])

def ct(dt): return dt-timedelta(hours=6)
def sess_blk(cd):
    m=cd.hour*60+cd.minute
    return (120<=m<150)or(450<=m<540)or(1380<=m<1410)or(900<=m<960)
def wknd(cd):
    return cd.weekday()==5 or (cd.weekday()==6 and (cd.hour*60+cd.minute)<1020) \
           or (cd.weekday()==4 and (cd.hour*60+cd.minute)>=960)

start=tr[0]["entry"]; end=tr[-1]["exit"]
total_span=(end-start).total_seconds()/60.0

# time IN trade
in_trade=sum((t["exit"]-t["entry"]).total_seconds()/60.0 for t in tr)

# idle stretches = exit[i] -> entry[i+1]; classify each minute
sess=wk=other=0
for i in range(len(tr)-1):
    a=tr[i]["exit"]; b=tr[i+1]["entry"]
    if b<=a: continue
    c=a.replace(second=0,microsecond=0)
    while c<b:
        x=ct(c)
        if wknd(x): wk+=1
        elif sess_blk(x): sess+=1
        else: other+=1
        c+=timedelta(minutes=1)

idle=sess+wk+other
def hm(m): return f"{int(m//60)}h{int(m%60):02d}m"
def days(m): return m/1440.0

print(f"OOS span: {start} -> {end}")
print(f"  total wall-clock : {hm(total_span)}  ({days(total_span):.1f} days)\n")
print(f"  IN TRADE         : {hm(in_trade):>10}  {in_trade/total_span*100:5.1f}%")
print(f"  IDLE total       : {hm(idle):>10}  {idle/total_span*100:5.1f}%")
print(f"    - weekend/closed: {hm(wk):>10}  {wk/total_span*100:5.1f}%")
print(f"    - session block : {hm(sess):>10}  {sess/total_span*100:5.1f}%")
print(f"    - OTHER (S/R,VWAP,deadzone,drought,no-signal):")
print(f"                      {hm(other):>10}  {other/total_span*100:5.1f}% of wall-clock")
print()
# reframe OTHER as % of TRADEABLE time (exclude weekend+session)
tradeable = total_span - wk - sess
print(f"  Of TRADEABLE time ({hm(tradeable)}, weekend+session removed):")
print(f"    in trade : {in_trade/tradeable*100:5.1f}%")
print(f"    OTHER idle (your S/R+VWAP+etc blocks): {other/tradeable*100:5.1f}%   = {hm(other)}")
