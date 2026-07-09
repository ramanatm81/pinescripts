#!/usr/bin/env python3
"""
Per-year validation of the MOMENTUM entry variants that beat baseline.
Confirms the aggregate +PnL isn't one lucky year (the fade-filters-hurt rule).

Candidates (all OFF exit = opposite zone edge, 1pt slip):
  A  MOM near15  swing50 pivot10 SL200   -> aggregate pf 1.20 (best pf)
  B  MOM  none   swing50 pivot5  SL200   -> aggregate pf 1.05 (best pnl, no gate)
  C  MOM  none   swing50 pivot10 SL200   -> aggregate pf 1.02 (plain flip)
  D  MOM near15  swing50 pivot5  SL200   -> gate + tight pivot combo
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from strategies import stats
from zone_rider_entry_fix import pivots, ZONE_WIDTH, COOLDOWN

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0

def load_5yr():
    H=[];L=[];C=[];TM=[];YR=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            H.append(h);L.append(l);C.append(c)
            TM.append(dt.hour*60+dt.minute); YR.append(dt.year)
    return dict(H=H,L=L,C=C,TM=TM,YR=YR,n=len(C))

def run_mom(d, min_swing, plen, sl_pts, near):
    """Momentum entry (long on swingUp, short on swingDown), OFF exit, optional proximity gate."""
    n=d["n"]; H=d["H"];L=d["L"];C=d["C"];TM=d["TM"]
    phv,plv=pivots(H,L,plen)
    resistance=support=None; inTrade=False; tradeDir=0; entry=0.0; cooldown=0
    trades=[]
    for i in range(n):
        m=TM[i]; eod=(900<=m<960)
        inBlock=(120<=m<150) or (450<=m<540) or (1020<=m<1050)
        if inTrade:
            if eod or inBlock:
                px=C[i]; trades.append((px-entry) if tradeDir==1 else (entry-px))
                inTrade=False; tradeDir=0; cooldown=0
            else:
                exited=False
                if tradeDir==1 and L[i]<=entry-sl_pts:
                    trades.append(-sl_pts); inTrade=False; tradeDir=0; cooldown=COOLDOWN; exited=True
                elif tradeDir==-1 and H[i]>=entry+sl_pts:
                    trades.append(-sl_pts); inTrade=False; tradeDir=0; cooldown=COOLDOWN; exited=True
                if not exited:
                    if tradeDir==1 and resistance is not None:
                        lvl=resistance+ZONE_WIDTH
                        if H[i]>=lvl: trades.append(lvl-entry); inTrade=False; tradeDir=0; cooldown=COOLDOWN
                    elif tradeDir==-1 and support is not None:
                        lvl=support-ZONE_WIDTH
                        if L[i]<=lvl: trades.append(entry-lvl); inTrade=False; tradeDir=0; cooldown=COOLDOWN
        swingUp=swingDown=False
        if phv[i] is not None:
            prev=resistance; resistance=phv[i]
            if prev is not None and (phv[i]-prev)>=min_swing: swingUp=True
        if plv[i] is not None:
            prev=support; support=plv[i]
            if prev is not None and (prev-plv[i])>=min_swing: swingDown=True
        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and (not eod) and (not inBlock) and cooldown==0:
            up_ok=dn_ok=True
            if near is not None:
                if swingUp   and resistance is not None: up_ok=abs(C[i]-resistance)<=near
                if swingDown and support    is not None: dn_ok=abs(C[i]-support)<=near
            if swingUp and up_ok:     inTrade=True; tradeDir=1;  entry=C[i]
            elif swingDown and dn_ok: inTrade=True; tradeDir=-1; entry=C[i]
    return trades

def adj(tr): return [t-SLIP for t in tr]

CANDS=[
    ("A MOM near15 pivot10", dict(min_swing=50,plen=10,sl_pts=200,near=15)),
    ("B MOM none   pivot5",  dict(min_swing=50,plen=5, sl_pts=200,near=None)),
    ("C MOM none   pivot10", dict(min_swing=50,plen=10,sl_pts=200,near=None)),
    ("D MOM near15 pivot5",  dict(min_swing=50,plen=5, sl_pts=200,near=15)),
]

if __name__=="__main__":
    print("loading 5yr…"); d=load_5yr(); print(f"bars {d['n']:,}\n")
    yrs=list(range(min(d['YR']),max(d['YR'])+1))
    for name,kw in CANDS:
        full=stats(adj(run_mom(d,**kw)))
        print(f"### {name}   [FULL] pnl={full['pnl']:.0f} win{full['winrate']:.0f}% n{full['n']} pf{full['pf']:.2f}")
        print("  year |   pnl  | win% |  n  | pf")
        pos=0
        for yr in yrs:
            idx=[i for i in range(d['n']) if d['YR'][i]==yr]
            sub={k:[d[k][i] for i in idx] for k in ("H","L","C","TM","YR")}; sub["n"]=len(idx)
            st=stats(adj(run_mom(sub,**kw)))
            if st['pnl']>0: pos+=1
            print(f"  {yr} | {st['pnl']:6.0f} | {st['winrate']:4.0f} | {st['n']:3d} | {st['pf']:.2f}")
        print(f"  --> profitable years: {pos}/{len(yrs)}\n")
