"""Quantify: do trades preceded by a BIG real gap (>median) behave differently,
and would a different SL help them?

Real gap = exit[i-1] -> entry[i], MINUS session-blocked minutes AND weekend
minutes (Fri close -> Sun/Mon reopen). Split trades by gap bucket. For each
bucket report win%/net AND adverse-excursion (MAE) distribution — the MAE is
what an SL decision hinges on. MNQ: 1 pt = $2, so SL 50pt=$100, 30pt=$60.
"""
import csv, os
from datetime import datetime, timedelta
from collections import defaultdict

PATH = os.path.expanduser("~/Downloads/input.csv")
rows = list(csv.DictReader(open(PATH, encoding="utf-8-sig")))
by_num = defaultdict(dict)
for r in rows:
    num = r["Trade number"].strip(); typ = r["Type"].strip()
    dt = datetime.strptime(r["Date and time"].strip(), "%Y-%m-%d %H:%M")
    if typ.startswith("Entry"):
        by_num[num]["entry"]=dt; by_num[num]["dir"]="L" if "long" in typ else "S"
    else:
        by_num[num]["exit"]=dt
        by_num[num]["reason"]=r["Signal"].strip()
        by_num[num]["pnl"]=float(r["Net PnL USD"])
        by_num[num]["mae"]=abs(float(r["Adverse excursion USD"]))  # $, positive
        by_num[num]["mfe"]=abs(float(r["Favorable excursion USD"]))
trades=[]
for num,d in by_num.items():
    if "entry" in d and "exit" in d:
        trades.append(dict(num=int(num), dir=d["dir"], entry=d["entry"], exit=d["exit"],
                           reason=d["reason"], pnl=d["pnl"], mae=d["mae"], mfe=d["mfe"]))
trades.sort(key=lambda t:t["num"])

def ct(dt): return dt - timedelta(hours=6)
def blocked(cd):
    m = cd.hour*60+cd.minute
    return (120<=m<150)or(450<=m<540)or(1380<=m<1410)or(900<=m<960)
def dead_minutes(a,b):
    """session-blocked OR weekend minutes in [a,b) (CT for blocks, weekday for wknd)."""
    if b<=a: return 0
    n=0; cur=a.replace(second=0,microsecond=0)
    while cur<b:
        c=ct(cur)
        # weekend: Sat all day, Sun before 17:00 CT (market reopens Sun 17:00 CT)
        wknd = c.weekday()==5 or (c.weekday()==6 and (c.hour*60+c.minute)<1020) \
               or (c.weekday()==4 and (c.hour*60+c.minute)>=960)  # Fri after 16:00 CT close
        if wknd or blocked(c): n+=1
        cur+=timedelta(minutes=1)
    return n

# preceding real gap for each trade (trade 0 has none)
for i,t in enumerate(trades):
    if i==0:
        t["gap"]=None; continue
    raw=(t["entry"]-trades[i-1]["exit"]).total_seconds()/60.0
    t["gap"]=max(raw-dead_minutes(trades[i-1]["exit"], t["entry"]), 0.0) if raw>0 else 0.0

g=[t for t in trades if t["gap"] is not None]
gv=sorted(x["gap"] for x in g); med=gv[len(gv)//2]
print(f"trades with a preceding gap: {len(g)}   median real gap = {med:.0f}m\n")

def stats(ts, lab):
    n=len(ts)
    if n==0: print(f"  {lab}: (none)"); return
    net=sum(t["pnl"] for t in ts); w=sum(1 for t in ts if t["pnl"]>0)
    mae=sorted(t["mae"] for t in ts)
    def p(q): return mae[int(q/100*(n-1))]
    # how many hit near the SL (MAE >= $60 ~ 30pt, >= $100 ~ 50pt)
    near60=sum(1 for t in ts if t["mae"]>=60); near100=sum(1 for t in ts if t["mae"]>=100)
    print(f"  {lab:<18} n={n:>3}  net={net:>+8.1f}  win%={w/n*100:>5.1f}  "
          f"avg={net/n:>+6.1f} | MAE med=${p(50):>5.1f} p90=${p(90):>6.1f} | "
          f"MAE>=$60:{near60:>3}({near60/n*100:.0f}%) >=$100:{near100:>3}({near100/n*100:.0f}%)")

print("=== SPLIT AT MEDIAN ===")
stats([t for t in g if t["gap"]<=med], "<= median (17m)")
stats([t for t in g if t["gap"]>med],  ">  median (17m)")

print("\n=== FINER BUCKETS ===")
for lo,hi,lab in [(0,17,"<=17m"),(17,30,"17-30m"),(30,60,"30-60m"),
                  (60,120,"60-120m"),(120,10**9,"120m+")]:
    stats([t for t in g if lo<=t["gap"]<hi], lab)

# For the >median trades: what were the LOSERS' MAE? would a tighter/wider SL help?
big=[t for t in g if t["gap"]>med]
print(f"\n=== >median losers: where did they die? (SL is ~$60-100) ===")
losers=[t for t in big if t["pnl"]<=0]
print(f"  {len(losers)} losers of {len(big)} big-gap trades")
by_reason=defaultdict(lambda:[0,0.0])
for t in losers: by_reason[t["reason"]][0]+=1; by_reason[t["reason"]][1]+=t["pnl"]
for r,(c,p) in sorted(by_reason.items(),key=lambda kv:kv[1][1]):
    print(f"    {r:<12} n={c:>3}  pnl={p:>+8.1f}")
