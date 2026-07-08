#!/usr/bin/env python3
"""Breach-fade tested as a MODE inside the faithful backtest.py engine (reuses its
exact SMA/stop/TP/session logic), so numbers are directly comparable to the +30,578
baseline. RAW pnl and 1pt-slip both shown."""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars,yrs

BASE=dict(slopeEntry=2.5,slAboveSma=50.0,slBelowSma=30.0,tpPts=50.0,tpMult=3.0,
          trailTrigger=30.0,trailDist=8.0,trailDistStrong=10.0,tExpBars=20,
          tExpHardBars=20,tExpHardSlope=1.0)

def stats(trs, slip):
    pnls=[t[3]-slip for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,win=0,pf=0,mdd=0,big=0)
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    r=0.0;peak=0.0;mdd=0.0
    for x in pnls:
        r+=x;peak=max(peak,r);mdd=max(mdd,peak-r)
    return dict(n=n,pnl=round(pnl),win=round(w/n*100,1),pf=round(gp/gl,2) if gl>0 else 999,
                mdd=round(mdd),big=round(min(pnls)))

def show(name, trs):
    raw=stats(trs,0.0); slp=stats(trs,1.0)
    print(f"{name}")
    print(f"   RAW : pnl={raw['pnl']:8} win{raw['win']:5}% n{raw['n']:6} pf{raw['pf']:.2f} mdd{raw['mdd']:7} bigLoss{raw['big']}")
    print(f"   1slp: pnl={slp['pnl']:8} win{slp['win']:5}% n{slp['n']:6} pf{slp['pf']:.2f} mdd{slp['mdd']:7} bigLoss{slp['big']}")

if __name__=="__main__":
    print("loading 5yr…"); bars,yrs=load(); print(f"bars {len(bars):,}\n")
    show("BASELINE (breach off)", bt.run(bars, dict(BASE)))
    print()
    show("BREACH-FADE + SL/TP (manage like normal)", bt.run(bars, dict(BASE, enableBreachFade=True, breachFadeBars=5, smoothSRPct=0.30, breachFadeSL=True)))
    print()
    show("BREACH-FADE no-SL (exit only on opp signal)", bt.run(bars, dict(BASE, enableBreachFade=True, breachFadeBars=5, smoothSRPct=0.30, breachFadeSL=False)))
