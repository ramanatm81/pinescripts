"""Two questions in one:
  (A) BIG-gap trades (>median): does WIDENING / removing the SL help (winners run)?
  (B) SMALL-gap trades (<=median, the weak 56%-win cohort): does TIGHTENING help?

Method: reprice each trade under a candidate SL of $X using MAE/MFE.
  stop_hit = MAE >= X  -> trade becomes -X
  else                 -> keep actual pnl
For WIDER-than-actual SL we can only *keep or improve* losers whose actual stop
was tighter than X — but the export's actual SL already fired at ~$60/$100, so a
trade that actually lost less than X was NOT stopped by SL; widening cannot change
those. Widening only matters for trades whose ACTUAL exit was the SL leg
(Exit-Long/Exit-Short) AND whose MFE shows they later recovered — the export
can't show post-stop recovery, so WIDENING is bounded: we can only say how much
LESS the SL-hit losers would lose if not stopped (unknowable) — so for widening we
report a DIFFERENT, honest metric: among actual SL-exit losers, how many had MFE
(favorable) >= Y, i.e. price DID later move Y in their favor (a wider stop MIGHT
have caught it). MNQ 1pt=$2.
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
        tr.append(dict(num=int(num),entry=d["entry"],exit=d["exit"],reason=d["reason"],
                       pnl=d["pnl"],mae=d["mae"],mfe=d["mfe"]))
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
big=[t for t in g if t["gap"]>med]; small=[t for t in g if t["gap"]<=med]

def sim(ts,SL):
    net=0.0;killed=0;klost=0.0;cut=0;saved=0.0
    for t in ts:
        if t["mae"]>=SL:
            net+=-SL
            if t["pnl"]>0: killed+=1; klost+=t["pnl"]+SL
            else:
                cut+=1
                if t["pnl"]<-SL: saved+=(-SL-t["pnl"])
        else: net+=t["pnl"]
    return net,killed,klost,cut,saved

def table(ts,lab):
    base=sum(t["pnl"] for t in ts); w=sum(1 for t in ts if t["pnl"]>0)
    print(f"\n### {lab}: n={len(ts)}  baseline net=${base:.1f}  win%={w/len(ts)*100:.1f}")
    print(f"{'SL':>7} {'pts':>4} | {'net':>9} {'vs base':>9} | win killed  loser cut")
    for pts in [70,60,50,40,35,30,25,20]:
        SL=pts*2.0; net,k,kl,c,s=sim(ts,SL)
        print(f"${SL:>5.0f} {pts:>4} | {net:>+9.1f} {net-base:>+9.1f} | "
              f"{k:>3}(-${kl:>6.0f}) {c:>3}(+${s:>5.0f})")

table(big,   "BIG-gap  (>median 17m)  — test tighten AND wider")
table(small, "SMALL-gap (<=median 17m) — the weak 56% cohort")

# widening probe: among ACTUAL SL-leg losers, did price later go favorable?
print("\n=== WIDEN probe: actual SL-exit losers whose MFE shows later favorable move ===")
for lab,ts in [("BIG",big),("SMALL",small)]:
    sl_losers=[t for t in ts if t["reason"] in ("Exit-Long","Exit-Short") and t["pnl"]<=0]
    if not sl_losers: print(f"  {lab}: none"); continue
    mfe_ge40=sum(1 for t in sl_losers if t["mfe"]>=40)
    print(f"  {lab}: {len(sl_losers)} SL-leg losers, "
          f"{mfe_ge40} had MFE>=$40 before stopping "
          f"(price DID move their way first — but they still stopped: SL not the problem)")
