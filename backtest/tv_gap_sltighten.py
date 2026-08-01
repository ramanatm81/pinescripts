"""Simulate TIGHTER SL on the >median-gap trades using MAE/MFE from the export.

For each trade we know: pnl, MAE (max $ against), MFE (max $ for). A candidate
SL of $X stops the trade IFF MAE >= X (price reached -X before exit).
  - If a WINNER had MAE >= X  -> it would have been KILLED (turned into a ~-X loss)
  - If a LOSER  had MAE >= X  -> it would have been CUT EARLY at -X (saved the
    difference between its actual loss and -X, IF actual loss was worse than -X)

Caveat (stated, not hidden): this assumes the -X touch happens BEFORE the final
exit, which is true by MAE definition, and that no winner that dipped to -X would
still have recovered post-stop (can't know — a stop is a stop). So this is an
UPPER bound on winners-killed and a fair estimate of losers-cut. MNQ 1pt=$2.
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
    else:
        bn[num]["exit"]=dt; bn[num]["reason"]=r["Signal"].strip()
        bn[num]["pnl"]=float(r["Net PnL USD"])
        bn[num]["mae"]=abs(float(r["Adverse excursion USD"]))
        bn[num]["mfe"]=abs(float(r["Favorable excursion USD"]))
tr=[]
for num,d in bn.items():
    if "entry" in d and "exit" in d:
        tr.append(dict(num=int(num),entry=d["entry"],exit=d["exit"],
                       reason=d["reason"],pnl=d["pnl"],mae=d["mae"],mfe=d["mfe"]))
tr.sort(key=lambda t:t["num"])

def ct(dt): return dt-timedelta(hours=6)
def blk(cd):
    m=cd.hour*60+cd.minute
    return (120<=m<150)or(450<=m<540)or(1380<=m<1410)or(900<=m<960)
def dead(a,b):
    if b<=a: return 0
    n=0; c=a.replace(second=0,microsecond=0)
    while c<b:
        x=ct(c)
        wknd=x.weekday()==5 or (x.weekday()==6 and (x.hour*60+x.minute)<1020) \
             or (x.weekday()==4 and (x.hour*60+x.minute)>=960)
        if wknd or blk(x): n+=1
        c+=timedelta(minutes=1)
    return n
for i,t in enumerate(tr):
    t["gap"]=None if i==0 else max((t["entry"]-tr[i-1]["exit"]).total_seconds()/60.0
                                   -dead(tr[i-1]["exit"],t["entry"]),0.0)
g=[t for t in tr if t["gap"] is not None]
med=sorted(x["gap"] for x in g)[len(g)//2]
big=[t for t in g if t["gap"]>med]
base_net=sum(t["pnl"] for t in big)
print(f">median trades: {len(big)}  baseline net=${base_net:.1f}  "
      f"(SL currently 30/50pt = $60/$100)\n")

def sim(SL_usd):
    net=0.0; killed=0; killed_lost=0.0; cut=0; saved=0.0; untouched=0
    for t in big:
        if t["mae"] >= SL_usd:            # would have been stopped at -SL
            net += -SL_usd
            if t["pnl"]>0: killed+=1; killed_lost += (t["pnl"]+SL_usd)  # gave up win + took -SL
            else:
                cut+=1
                if t["pnl"] < -SL_usd: saved += (-SL_usd - t["pnl"])    # loss was worse than -SL
        else:
            net += t["pnl"]; untouched+=1
    return net,killed,killed_lost,cut,saved,untouched

print(f"{'SL':>8} {'~pts':>5} | {'net':>9} {'vs base':>9} | {'winners killed':>15} {'losers cut':>11} {'untouched':>9}")
for pts in [50,40,35,30,25,20]:
    SL=pts*2.0
    net,killed,klost,cut,saved,unt=sim(SL)
    print(f"${SL:>6.0f} {pts:>5} | {net:>+9.1f} {net-base_net:>+9.1f} | "
          f"{killed:>4} (-${klost:>6.0f} lost) {cut:>4} (+${saved:>5.0f}) {unt:>9}")
