import csv, math, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import v_fade_test as vf

CSV5 = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
RECENT = "/Users/maheshk81/Downloads/data.csv"

def load5():
    bars=[]
    with open(CSV5) as f:
        for r in csv.DictReader(f):
            try: o=float(r["open"]);h=float(r["high"]);l=float(r["low"]);c=float(r["close"])
            except: continue
            dt=datetime.fromisoformat(r["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c))
    return bars

def trade_entrystop(bars, ev, stopPts, trailTrig, trailDist, slip):
    H=[b[2] for b in bars]; L=[b[3] for b in bars]; C=[b[4] for b in bars]; O=[b[1] for b in bars]
    trades=[]
    for e in ev:
        i0=e["bar"]
        if i0+1>=len(bars): continue
        entry=O[i0+1]; start=i0+2
        if start>=len(bars): continue
        dirn=1 if e["kind"]=="V" else -1
        stop= entry-stopPts if dirn==1 else entry+stopPts
        best=entry; trailStop=None; exitP=None
        for i in range(start,len(bars)):
            h=H[i];l=L[i]
            if dirn==1:
                best=max(best,h)
                if best-entry>=trailTrig: ts=best-trailDist; trailStop=ts if trailStop is None else max(trailStop,ts)
                if l<=stop: exitP=stop; break
                if trailStop is not None and l<=trailStop: exitP=trailStop; break
            else:
                best=min(best,l)
                if entry-best>=trailTrig: ts=best+trailDist; trailStop=ts if trailStop is None else min(trailStop,ts)
                if h>=stop: exitP=stop; break
                if trailStop is not None and h>=trailStop: exitP=trailStop; break
        if exitP is None: exitP=C[-1]; i=len(bars)-1
        pnl=((exitP-entry) if dirn==1 else (entry-exitP))-slip
        trades.append(dict(kind=e["kind"], pnl=pnl, bars=i-i0, year=bars[i0][0].year))
    return trades

def rep(tr, label, only=None):
    if only: tr=[t for t in tr if t["kind"]==only]
    n=len(tr)
    if n==0: print(f"{label}: 0"); return
    net=sum(t["pnl"] for t in tr); w=[t for t in tr if t["pnl"]>0]
    gw=sum(t["pnl"] for t in w); gl=sum(t["pnl"] for t in tr if t["pnl"]<=0)
    pf=gw/abs(gl) if gl else 99
    print(f"{label}: {n} tr  net {net:.0f} (${net*2:.0f})  PF {pf:.2f}  win {len(w)/n*100:.0f}%")

if __name__=="__main__":
    print("loading 5yr..."); bars=load5()
    print(f"{len(bars):,} bars {bars[0][0].date()}->{bars[-1][0].date()}")
    det=dict(vBars=60, legMinAbs=12.0, legAtrMult=2.5, apexTol=0.20, minLegAngle=9.0, maxAngleGap=6.0, useGeom=True)
    print("detecting (session-adaptive 2.5xATR floor12, heavy)...")
    ev=vf.detect(bars, det)
    nv=sum(1 for e in ev if e["kind"]=="V"); niv=sum(1 for e in ev if e["kind"]=="IV")
    print(f"detected {nv} V + {niv} ^ = {nv+niv} signals over 5yr  (vs 1762 with old fixed-80)\n")

    print("=== ENTRY-BASED stop (entry +/- x), honest next-open fill ===")
    for slip in (0.0,1.0):
        for sp in [30,50]:
            tr=trade_entrystop(bars, ev, sp, 70.0, 20.0, slip)
            print(f"-- stop{sp} trail70/20 slip{slip} --")
            rep(tr, "  both legs")
            rep(tr, "  V->LONG ", only="V")
            rep(tr, "  ^->SHORT", only="IV")
    print()
    print("=== PER-YEAR (stop30 trail70/20 raw, both legs) ===")
    tr=trade_entrystop(bars, ev, 30.0, 70.0, 20.0, 0.0)
    yr=defaultdict(lambda:[0,0.0])
    for t in tr: yr[t["year"]][0]+=1; yr[t["year"]][1]+=t["pnl"]
    for y in sorted(yr): print(f"  {y}  {yr[y][0]:>4} tr  {yr[y][1]:>8.0f} pts")
