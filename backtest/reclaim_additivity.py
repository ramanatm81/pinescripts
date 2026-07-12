#!/usr/bin/env python3
"""
ADDITIVITY TEST: does the deep-fade band-reclaim (SL40) make money when the validated
slope BASE is idle or losing? Runs both on the same 5yr bars, compares:
  - base alone / reclaim alone / naive sum
  - per-YEAR breakdown (does reclaim lift the base's weak years, esp 2024?)
  - per-DAY P&L correlation (low/negative corr => genuinely additive, diversifying)
  - reclaim's contribution ON DAYS the base lost money
Both at 0 slip and 1pt slip.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt
import slope_band_reclaim as rc

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
YEARS=[2021,2022,2023,2024,2025,2026]

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10, enableThrdReversal=False)
RECLAIM = dict(lookback=10, lbBand=10, slPts=40.0, trailTrigger=30.0, trailDist=8.0,
               trailDistStrong=10.0, cooldownBars=10, deepSlope=7, minPierce=10.0,
               enableSRFilter=True, srHalfWidth=10, srZoneWidth=25.0)

def daykey(dt): return (dt.year,dt.month,dt.day)

def pnl_by_day(trades, slip, dt_idx):
    """trades: base uses (dir,entry,exit,pnl,reason,deep,dt); reclaim uses (1,e,x,pnl,reason,dt,heat)."""
    d=defaultdict(float)
    for t in trades:
        pnl=t[3]-slip; dt=t[dt_idx]
        d[daykey(dt)] += pnl
    return d

def year_of(dk): return dk[0]

def corr(a,b):
    keys=set(a)|set(b); xs=[a.get(k,0.0) for k in keys]; ys=[b.get(k,0.0) for k in keys]
    n=len(xs)
    if n<2: return float('nan')
    mx=sum(xs)/n; my=sum(ys)/n
    sxy=sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    sxx=sum((x-mx)**2 for x in xs); syy=sum((y-my)**2 for y in ys)
    if sxx==0 or syy==0: return float('nan')
    return sxy/(sxx**0.5*syy**0.5)

if __name__=="__main__":
    print("loading bars + VWAP bands…")
    bars, vol = rc.load()
    bands = rc.vwap_bands(bars, vol)
    # base expects bars only (no vol); its port reads the same tuple shape
    print(f"bars {len(bars):,}  running base…")
    base_tr = bt.run(bars, BASE)
    print(f"base trades {len(base_tr)}   running reclaim…")
    rc_tr = rc.run(bars, vol, bands, RECLAIM)
    print(f"reclaim trades {len(rc_tr)}")

    for slip in (0.0,1.0):
        bd = pnl_by_day(base_tr, slip, 6)   # base dt at index 6
        rd = pnl_by_day(rc_tr,  slip, 5)    # reclaim dt at index 5
        allkeys=set(bd)|set(rd)
        print(f"\n########## slippage {slip}/trade ##########")
        # per-year
        print(f"{'year':>6} | {'base':>8} {'reclaim':>8} {'combined':>9} | {'base+yr':>7} {'comb+yr':>7}")
        bt_tot=rt_tot=ct_tot=0.0
        for y in YEARS:
            b=sum(v for k,v in bd.items() if k[0]==y)
            r=sum(v for k,v in rd.items() if k[0]==y)
            print(f"{y:>6} | {b:>8.0f} {r:>8.0f} {b+r:>9.0f} |")
            bt_tot+=b; rt_tot+=r; ct_tot+=b+r
        print(f"{'TOT':>6} | {bt_tot:>8.0f} {rt_tot:>8.0f} {ct_tot:>9.0f}")
        # day-level correlation
        print(f"per-day P&L correlation base vs reclaim: {corr(bd,rd):+.3f}")
        # reclaim's edge on days base LOST
        base_down_days = [k for k in bd if bd[k]<0]
        rc_on_down = sum(rd.get(k,0.0) for k in base_down_days)
        rc_on_down_n = sum(1 for k in base_down_days if k in rd)
        print(f"base losing days: {len(base_down_days)}   reclaim P&L on those days: {rc_on_down:+.0f} over {rc_on_down_n} days")
        # reclaim on days base was FLAT (no base trade)
        base_flat = [k for k in rd if k not in bd]
        print(f"reclaim traded on {len(base_flat)} days the base was FLAT, P&L there: {sum(rd[k] for k in base_flat):+.0f}")
