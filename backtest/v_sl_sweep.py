import csv, sys
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

def ctm(dt):
    ct=dt.astimezone(timezone(timedelta(hours=-5))); return ct.hour*60+ct.minute

# Honest sim matching the Pine: one position at a time, lockout(60), EOD block,
# entry = next bar open, stop = entry +/- slPts, MFE trail trig/dist, exits from i0+2.
def run(bars, ev, slPts, trailTrig, trailDist, slip, lockout=60, side="both"):
    H=[b[2] for b in bars]; L=[b[3] for b in bars]; C=[b[4] for b in bars]; O=[b[1] for b in bars]
    trades=[]; inpos_until=-1; lock_until=-1
    for e in ev:
        i0=e["bar"]
        if side=="V" and e["kind"]!="V": continue
        if side=="IV" and e["kind"]!="IV": continue
        if i0<=inpos_until or i0<=lock_until: continue
        cm=ctm(bars[i0][0])
        if 840<=cm<960: continue   # EOD block + hard window
        if i0+2>=len(bars): continue
        entry=O[i0+1]; dirn=1 if e["kind"]=="V" else -1
        stop= entry-slPts if dirn==1 else entry+slPts
        best=entry; trailStop=None; exitP=None; exitbar=len(bars)-1
        for i in range(i0+2,len(bars)):
            h=H[i];l=L[i]
            if dirn==1:
                best=max(best,h)
                if best-entry>=trailTrig: ts=best-trailDist; trailStop=ts if trailStop is None else max(trailStop,ts)
                if l<=stop: exitP=stop; exitbar=i; break
                if trailStop is not None and l<=trailStop: exitP=trailStop; exitbar=i; break
            else:
                best=min(best,l)
                if entry-best>=trailTrig: ts=best+trailDist; trailStop=ts if trailStop is None else min(trailStop,ts)
                if h>=stop: exitP=stop; exitbar=i; break
                if trailStop is not None and h>=trailStop: exitP=trailStop; exitbar=i; break
        if exitP is None: exitP=C[-1]
        pnl=((exitP-entry) if dirn==1 else (entry-exitP))-slip
        trades.append(dict(kind=e["kind"], pnl=pnl, year=bars[i0][0].year))
        inpos_until=exitbar; lock_until=i0+lockout
    return trades

def line(tr, label):
    n=len(tr)
    if n==0: return f"{label}: 0 tr"
    net=sum(t["pnl"] for t in tr); w=[t for t in tr if t["pnl"]>0]
    gw=sum(t["pnl"] for t in w); gl=sum(t["pnl"] for t in tr if t["pnl"]<=0)
    pf=gw/abs(gl) if gl else 99
    return f"{label}: {n:>4} tr  net {net:>7.0f} (${net*2:>7.0f})  PF {pf:.2f}  win {len(w)/n*100:.0f}%"

def sweep(bars, ev, tag, slip):
    print(f"\n=== {tag}  (slip {slip}) ===")
    for sl in [50,75,100,125,150,175,200]:
        print(f" SL {sl}:")
        print("   ", line(run(bars,ev,sl,70,20,slip,side="both"), "both"))
        print("   ", line(run(bars,ev,sl,70,20,slip,side="V"),    "V->LONG "))
        print("   ", line(run(bars,ev,sl,70,20,slip,side="IV"),   "^->SHORT"))

if __name__=="__main__":
    det=dict(vBars=60, legMinAbs=12.0, legAtrMult=2.5, apexTol=0.20, minLegAngle=9.0, maxAngleGap=6.0, useGeom=True)
    print("RECENT data.csv...")
    br=vf.load(RECENT); evr=vf.detect(br, det)
    sweep(br, evr, "3-WEEK recent (data.csv)", 0.0)
    sweep(br, evr, "3-WEEK recent (data.csv)", 1.0)
    print("\nloading + detecting 5yr (heavy)...")
    b5=load5(); ev5=vf.detect(b5, det)
    sweep(b5, ev5, "5-YEAR", 0.0)
    sweep(b5, ev5, "5-YEAR", 1.0)
