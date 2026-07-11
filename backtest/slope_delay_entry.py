#!/usr/bin/env python3
"""
Slope strategy — DELAYED ENTRY for extreme-slope ABOVE-SMA signals (per user 2026-07-11):
  When close>SMA and |slope|>=delayExtremeSlope at a would-be entry, don't enter now;
  wait delayBars, then enter same dir ONLY IF the slope signal is still valid.
Base = validated: noTHRD entries + VWAP proximity ±15.
Sweep delayBars {2,3,5} x delayExtremeSlope {8,10,12}. Per-year, 0 slip + 1pt.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
KSIGMA=2.0
BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10, enableThrdReversal=False)

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
    out=[]; curday=None; cumV=0.0; cumPV=0.0; cumPPV=0.0
    for (dt,o,h,l,c,m),v in zip(bars,vol):
        tp=(h+l+c)/3.0
        if dt.date()!=curday: curday=dt.date(); cumV=0.0; cumPV=0.0; cumPPV=0.0
        vv=v if v>0 else 1.0
        cumV+=vv; cumPV+=tp*vv; cumPPV+=tp*tp*vv
        mean=cumPV/cumV; var=max(cumPPV/cumV-mean*mean,0.0); sd=var**0.5
        out.append((mean,mean+KSIGMA*sd,mean-KSIGMA*sd,2*KSIGMA*sd))
    return out

def make_block(bars, bands, X):
    blk=[False]*len(bars)
    if X<=0: return blk
    for bi,(dt,o,h,l,c,m) in enumerate(bars):
        mean,up,lo,w=bands[bi]
        if w<1.0: continue
        if abs(c-up)<=X or abs(c-lo)<=X: blk[bi]=True
    return blk

def summ(trs, slip, years):
    p=[t[3]-slip for t in trs]; n=len(p)
    if n==0: return (0,0,0,0,[0]*len(years),0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    yl=[]; pos=0
    for y in years:
        yy=round(sum(t[3]-slip for t in trs if t[6].year==y))
        if yy>0: pos+=1
        yl.append(yy)
    return (round(sum(p)), n, round(gp/gl,2) if gl>0 else 999, round(100*w/n,1), yl, pos)

if __name__=="__main__":
    print("loading + VWAP bands…"); bars,vol=load(); bands=vwap_bands(bars,vol)
    years=[2021,2022,2023,2024,2025,2026]
    blk=make_block(bars,bands,15.0)
    baseP=dict(BASE, vwap_block=blk)
    base_trs=bt.run(bars, baseP)
    print(f"bars {len(bars):,}  base trades {len(base_trs)}\n")
    for slip in [0.0,1.0]:
        print(f"########## slippage {slip}/trade ##########")
        pnl,n,pf,win,yl,pos=summ(base_trs,slip,years)
        print(f"{'baseline':>18} | {pnl:>7} {n:>6} {pf:>5} {win:>5} | {pos}/6 | {yl}")
        for th in [8,10,12]:
            for d in [2,3,5]:
                trs=bt.run(bars, dict(baseP, delayExtremeSlope=float(th), delayBars=int(d)))
                pnl,n,pf,win,yl,pos=summ(trs,slip,years)
                print(f"{('slope>=%d delay%d'%(th,d)):>18} | {pnl:>7} {n:>6} {pf:>5} {win:>5} | {pos}/6 | {yl}")
        print()
