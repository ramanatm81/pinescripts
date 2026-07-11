#!/usr/bin/env python3
"""
Slope strategy (noTHRD-entry config) + VWAP-zone PROXIMITY FILTER (per user 2026-07-11):
  Don't take a NEW entry when close is within X pts of EITHER VWAP band (+2σ / −2σ).
  Skip the filter when bands aren't formed yet (σ ~ 0 early session).
  Sweep X in {0(off),5,10,15,20,30,40}. Per-year, 0 slip (to match +33,457 baseline) and 1pt.

VWAP bands = daily-anchored, volume-weighted 2σ (same as drawn in slope_strategy.pine).
"""
import csv, sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
KSIGMA=2.0
BAND_MIN=1.0   # if band width < this, treat as not-formed -> don't block
BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10,
            enableThrdReversal=False)   # noTHRD-entry = validated +33,457 base

def load():
    bars=[]; vol=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
                v=float(row.get("Volume") or row.get("volume") or 0.0)
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute)); vol.append(v)
    return bars, vol

def vwap_bands(bars, vol):
    """daily-anchored cumulative VWAP ±2σ. Returns list of (mean,up,lo,width)."""
    out=[]; curday=None; cumV=0.0; cumPV=0.0; cumPPV=0.0
    for (dt,o,h,l,c,m),v in zip(bars,vol):
        tp=(h+l+c)/3.0
        if dt.date()!=curday: curday=dt.date(); cumV=0.0; cumPV=0.0; cumPPV=0.0
        vv=v if v>0 else 1.0
        cumV+=vv; cumPV+=tp*vv; cumPPV+=tp*tp*vv
        mean=cumPV/cumV; var=max(cumPPV/cumV-mean*mean,0.0); sd=var**0.5
        up=mean+KSIGMA*sd; lo=mean-KSIGMA*sd
        out.append((mean,up,lo,up-lo))
    return out

def make_block(bars, bands, X):
    """block[bi]=True when close within X of +2σ or −2σ (and band is formed)."""
    blk=[False]*len(bars)
    if X<=0: return blk
    for bi,(dt,o,h,l,c,m) in enumerate(bars):
        mean,up,lo,w = bands[bi]
        if w < BAND_MIN:   # not formed early session -> don't block
            continue
        if abs(c-up)<=X or abs(c-lo)<=X:
            blk[bi]=True
    return blk

def summ(trs, slip, years):
    p=[t[3]-slip for t in trs]; n=len(p)
    if n==0: return (0,0,0,0,[0]*len(years),0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    yline=[]; pos=0
    for y in years:
        yy=round(sum(t[3]-slip for t in trs if t[6].year==y))
        if yy>0: pos+=1
        yline.append(yy)
    return (round(sum(p)), n, round(gp/gl,2) if gl>0 else 999, round(100*w/n,1), yline, pos)

if __name__=="__main__":
    print("loading + VWAP bands…"); bars,vol=load(); bands=vwap_bands(bars,vol)
    years=[2021,2022,2023,2024,2025,2026]
    print(f"bars {len(bars):,}\n")
    for slip in [0.0, 1.0]:
        print(f"########## slippage {slip}/trade ##########")
        print(f"{'proximity':>10} | {'pnl':>7} {'n':>6} {'pf':>5} {'win':>5} | +yr | per-year")
        for X in [0,5,10,15,20,30,40]:
            blk=make_block(bars,bands,X)
            params=dict(BASE, vwap_block=blk)
            trs=bt.run(bars, params)
            pnl,n,pf,win,yline,pos=summ(trs,slip,years)
            lab="off" if X==0 else f"±{X}pt"
            print(f"{lab:>10} | {pnl:>7} {n:>6} {pf:>5} {win:>5} | {pos}/6 | {yline}")
        print()
