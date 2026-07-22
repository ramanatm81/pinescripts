import csv, math, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import v_fade_test as vf

CSV5 = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

def load5():
    bars=[]
    with open(CSV5) as f:
        for r in csv.DictReader(f):
            try: o=float(r["open"]);h=float(r["high"]);l=float(r["low"]);c=float(r["close"])
            except: continue
            dt=datetime.fromisoformat(r["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c))
    return bars

def report(tr, label, only=None):
    if only:
        tr=[t for t in tr if t["kind"]==only]
    n=len(tr)
    if n==0: print(label,"0 tr"); return
    net=sum(t["pnl"] for t in tr); w=[t for t in tr if t["pnl"]>0]
    gw=sum(t["pnl"] for t in w); gl=sum(t["pnl"] for t in tr if t["pnl"]<=0)
    pf=gw/abs(gl) if gl else 99; ab=sum(t["bars"] for t in tr)/n
    print(f"{label}: {n} tr  net {net:.0f} (${net*2:.0f})  PF {pf:.2f}  win {len(w)/n*100:.0f}%  bars {ab:.0f}  worst {min(t['pnl'] for t in tr):.0f}")

if __name__=="__main__":
    print("loading 5yr..."); bars=load5()
    print(f"{len(bars):,} bars {bars[0][0].date()}->{bars[-1][0].date()}")
    det=dict(vBars=60, legMinAbs=80.0, apexTol=0.20, minLegAngle=9.0, maxAngleGap=6.0, useGeom=True)
    print("detecting V/^ (heavy)...")
    ev=vf.detect(bars, det)
    nv=sum(1 for e in ev if e["kind"]=="V"); niv=sum(1 for e in ev if e["kind"]=="IV")
    print(f"detected {nv} V, {niv} inverse-V over 5yr\n")

    print("=== WITH-reversal: V->LONG, IV->SHORT ===")
    for slip in (0.0,1.0):
        for sb in [30,50]:
            tr=vf.trade(bars, ev, dict(stopBeyond=float(sb), trailTrig=70.0, trailDist=20.0, slip=slip))
            print(f"-- stop{sb} trail70/20 slip{slip} --")
            report(tr, "  both legs")
            report(tr, "  V->LONG only ", only="V")
            report(tr, "  IV->SHORT only", only="IV")
    print()
    print("=== PER-YEAR (stop30 trail70/20 raw) ===")
    tr=vf.trade(bars, ev, dict(stopBeyond=30.0, trailTrig=70.0, trailDist=20.0, slip=0.0))
    # attach year via entry bar
    yrboth=defaultdict(lambda:[0,0.0]); yrlong=defaultdict(lambda:[0,0.0])
    for t,e in zip(tr,ev):
        y=bars[e["bar"]][0].year
        yrboth[y][0]+=1; yrboth[y][1]+=t["pnl"]
        if t["kind"]=="V": yrlong[y][0]+=1; yrlong[y][1]+=t["pnl"]
    print("year   both(n/pts)      V->LONG(n/pts)")
    for y in sorted(yrboth):
        b=yrboth[y]; lg=yrlong[y]
        print(f"  {y}  {b[0]:>4}/{b[1]:>7.0f}    {lg[0]:>4}/{lg[1]:>7.0f}")
