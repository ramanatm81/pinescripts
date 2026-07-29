#!/usr/bin/env python3
"""
Faithful port of live_trend.pine (DETECTOR ONLY, no trades). Measures each
trend's lifespan: bars & wall-clock from the START dot to the BREAK.

Params for this run (user): winMin=60, pullbackPts(giveback)=300.
Defaults kept: winMax=240, winStep=10, runMinPts=150, minR2=0.75,
reEntryFrac=0.7, pickBest=True.

START dot = latch bar (bar_index where the window qualifies). We time trends
from the dot bar (what you see on the chart), NOT the OLS anchor.
BREAK = close pulls back pullbackPts off the running extreme.
Duration(bars) = break_bar - start_bar. Duration(min) via bar timestamps.

Exclusion: drop any trend whose START dot bar falls in NY open
  = LDN 14:30-15:30 = CT 08:30-09:30 (CT minutes 510-569 inclusive of 08:30..09:29).
Timestamps in the port are normalized to America/Chicago (UTC-5).
"""
import csv, os, sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import statistics as st

CSV = os.environ.get("BACKTEST_DATA",
    "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv")

# --- params ---
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
PULLBACK = 300.0
REENTRY_FRAC = 0.7
PICKBEST = True

def load():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            t=row["time"]
            if not t: continue
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError): continue
            dt=datetime.fromisoformat(t).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c))
    return bars

def ols(closes, end, N):
    if end-N+1<0: return None,None
    yRef=closes[end-(N-1)]
    sx=sy=sxx=syy=sxy=0.0
    for i in range(N):
        x=float(N-1-i); y=closes[end-i]-yRef
        sx+=x;sy+=y;sxx+=x*x;syy+=y*y;sxy+=x*y
    fN=float(N)
    varX=sxx-sx*sx/fN; varY=syy-sy*sy/fN; covXY=sxy-sx*sy/fN
    if varX>0 and varY>0:
        return covXY/varX, (covXY*covXY)/(varX*varY)
    return None,None

def in_ny_open(dt):
    # CT 08:30-09:29  (LDN 14:30-15:29)
    m = dt.hour*60 + dt.minute
    return 510 <= m <= 569

def detect(bars):
    closes=[b[4] for b in bars]; n=len(bars)
    state=0; anchorBar=None; startPrice=None; liveSlope=None; liveDir=0; liveExtreme=None
    lockDir=0; lockExtreme=None; lockTravel=None
    startBar=None; startDt=None
    trends=[]  # (startDir, startBar, startDt, breakBar, breakDt, durBars, durMin, travel, extreme)
    for i in range(n):
        dt,o,h,l,c=bars[i]
        if lockDir!=0 and lockExtreme is not None:
            need=REENTRY_FRAC*lockTravel
            if lockDir<0 and h>=lockExtreme+need: lockDir=0
            elif lockDir>0 and l<=lockExtreme-need: lockDir=0
        if state==0:
            dS=None;dR=None;dN=None
            N=WINMIN
            while N<=min(WINMAX,4990):
                if N>=3 and i>=N-1:
                    s,r2=ols(closes,i,N)
                    if s is not None:
                        run=abs(s)*float(N-1)
                        if run>=RUNMIN and r2>=MINR2:
                            d=1 if s>0 else -1
                            if d!=lockDir and (dN is None or (PICKBEST and r2>dR)):
                                dS=s;dR=r2;dN=N
                N+=WINSTEP
            if dN is not None:
                state=1; liveDir=1 if dS>0 else -1
                startPrice=closes[i-(dN-1)]
                liveExtreme=h if liveDir>0 else l
                startBar=i; startDt=dt  # dot fires at THIS bar
        else:
            liveExtreme=max(liveExtreme,h) if liveDir>0 else min(liveExtreme,l)
            broke=(liveDir>0 and c<liveExtreme-PULLBACK) or (liveDir<0 and c>liveExtreme+PULLBACK)
            if broke:
                durBars=i-startBar
                durMin=(dt-startDt).total_seconds()/60.0
                travel=abs(liveExtreme-startPrice)
                trends.append((liveDir,startBar,startDt,i,dt,durBars,durMin,travel,liveExtreme))
                lockDir=liveDir; lockExtreme=liveExtreme
                lockTravel=max(abs(liveExtreme-startPrice),1.0)
                state=0; liveDir=0; liveExtreme=None
    return trends

def pctl(vals,p):
    if not vals: return 0
    vals=sorted(vals); k=(len(vals)-1)*p/100.0
    f=int(k); return vals[f] if f+1>=len(vals) else vals[f]+(vals[f+1]-vals[f])*(k-f)

def report(trends, name):
    kept=[t for t in trends if not in_ny_open(t[2])]
    excl=[t for t in trends if in_ny_open(t[2])]
    print(f"\n{'='*74}\n{name}  —  winMin=60, giveback=300pt, NY-open starts EXCLUDED\n{'='*74}")
    print(f"total trends detected : {len(trends)}")
    print(f"  excluded (NY open)  : {len(excl)}")
    print(f"  kept                : {len(kept)}")
    if not kept:
        return
    for lbl,sub in (("ALL kept",kept),
                    ("UP (green dot)",[t for t in kept if t[0]>0]),
                    ("DOWN (red dot)",[t for t in kept if t[0]<0])):
        db=[t[5] for t in sub]; dm=[t[6] for t in sub]; tv=[t[7] for t in sub]
        if not sub:
            print(f"\n  {lbl}: none"); continue
        print(f"\n  {lbl}: {len(sub)} trends")
        print(f"    duration bars : median {st.median(db):.0f}  mean {st.mean(db):.0f}  "
              f"min {min(db):.0f}  p25 {pctl(db,25):.0f}  p75 {pctl(db,75):.0f}  max {max(db):.0f}")
        print(f"    duration mins : median {st.median(dm):.0f}  mean {st.mean(dm):.0f}  "
              f"(= {st.median(dm)/60:.1f}h median, {max(dm)/60:.1f}h max)")
        print(f"    travel pts    : median {st.median(tv):.0f}  mean {st.mean(tv):.0f}  max {max(tv):.0f}")

def run_file(path,name):
    global CSV
    CSV=path
    bars=load()
    print(f"\n######## {name}  ({len(bars):,} bars, {bars[0][0].date()}..{bars[-1][0].date()}) ########")
    report(detect(bars), name)

if __name__=="__main__":
    run_file("/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv","5-YEAR")
    run_file("/Users/maheshk81/Downloads/data.csv","OOS")
