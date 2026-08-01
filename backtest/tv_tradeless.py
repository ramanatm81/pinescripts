"""With session filters ON, where is the strategy TRADELESS for non-session reasons?

Ground truth = your real TV export. For each exit->next-entry gap, strip out
minutes that fall inside a session-block window (LNOpen/PreNY/ETH/EOD, CT) AND
weekend/market-closed minutes. What REMAINS is idle time the session filters do
NOT explain -> S/R zone block, VWAP proximity block, dead-zone, drought, flat
slope, or simply no qualifying signal.

Reports the non-session idle stretches ranked, with the trades bracketing each
so you can go look at the chart and see which rule was holding you out.
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
    if typ.startswith("Entry"):
        bn[num]["entry"]=dt; bn[num]["dir"]="L" if "long" in typ else "S"
        bn[num]["esig"]=r["Signal"].strip()
    else:
        bn[num]["exit"]=dt; bn[num]["reason"]=r["Signal"].strip()
        bn[num]["pnl"]=float(r["Net PnL USD"])
tr=[]
for num,d in bn.items():
    if "entry" in d and "exit" in d:
        tr.append(dict(num=int(num),dir=d["dir"],entry=d["entry"],exit=d["exit"],
                       reason=d["reason"],pnl=d["pnl"]))
tr.sort(key=lambda t:t["num"])

def ct(dt): return dt-timedelta(hours=6)   # London -> CT
def sess_blk(cd):
    m=cd.hour*60+cd.minute
    return (120<=m<150)or(450<=m<540)or(1380<=m<1410)or(900<=m<960)
def wknd(cd):
    return cd.weekday()==5 or (cd.weekday()==6 and (cd.hour*60+cd.minute)<1020) \
           or (cd.weekday()==4 and (cd.hour*60+cd.minute)>=960)

def split_minutes(a,b):
    """return (session_min, weekend_min, other_idle_min) for [a,b)."""
    s=w=o=0; c=a.replace(second=0,microsecond=0)
    while c<b:
        x=ct(c)
        if wknd(x): w+=1
        elif sess_blk(x): s+=1
        else: o+=1
        c+=timedelta(minutes=1)
    return s,w,o

stretches=[]
for i in range(len(tr)-1):
    a=tr[i]["exit"]; b=tr[i+1]["entry"]
    if b<=a: continue
    s,w,o=split_minutes(a,b)
    stretches.append(dict(fro=a,to=b,sess=s,wknd=w,other=o,
                          after=tr[i]["reason"], nxt=tr[i+1]["dir"],
                          nxtpnl=tr[i+1]["pnl"], nxtsig=tr[i+1].get("esig","")))

others=sorted(x["other"] for x in stretches)
n=len(others)
def p(q): return others[int(q/100*(n-1))]
print(f"gaps: {n}   NON-SESSION idle (min): median={p(50):.0f}  mean={sum(others)/n:.1f}  "
      f"p90={p(90):.0f}  p95={p(95):.0f}  max={max(others):.0f}\n")

buckets=[(0,15),(15,30),(30,60),(60,120),(120,240),(240,10**9)]
labs=["<15m","15-30m","30-60m","1-2h","2-4h","4h+"]
print("NON-SESSION tradeless-stretch distribution:")
for (lo,hi),lab in zip(buckets,labs):
    c=sum(1 for v in others if lo<=v<hi)
    print(f"  {lab:>7}: {c:>4} ({c/n*100:4.1f}%)")

print("\nTop 25 longest NON-SESSION tradeless stretches (session+weekend removed):")
print(f"{'from exit':>13} -> {'to entry':>13} | {'OTHER':>6} {'sess':>5} {'wknd':>6} | after-exit -> next")
for g in sorted(stretches,key=lambda g:-g["other"])[:25]:
    print(f"{g['fro'].strftime('%m-%d %H:%M'):>13} -> {g['to'].strftime('%m-%d %H:%M'):>13} | "
          f"{g['other']:>5.0f}m {g['sess']:>4.0f}m {g['wknd']:>5.0f}m | "
          f"[{g['after']}] -> {g['nxt']} {g['nxtpnl']:+.0f} [{g['nxtsig']}]")
