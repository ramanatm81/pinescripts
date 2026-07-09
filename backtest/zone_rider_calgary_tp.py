#!/usr/bin/env python3
"""
Zone Rider "Calgary" + greedy TP test:
  - ADD a fixed take-profit (default 100 pts).
  - REMOVE all session blocks (no BLK, no EOD flatten) — trade around the clock.
  - Everything else same as Calgary (smoothed break entry, gap-convergence exit, hard SL).

Tests the winner config (smooth 1.0 / gap 40 / sl 300) and the current default
(gap 70 / sl 200), each WITH the 100pt TP and no session blocks.
"""
import csv, sys
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0
PIVOT_LEN = 10
ZONE_WIDTH = 25.0
COOLDOWN = 20

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((h,l,c)); yrs.append(dt.year)   # NOTE: no session minute — sessions removed
    return bars,yrs

def precompute_pivots(bars):
    n=len(bars); highs=[b[0] for b in bars]; lows=[b[1] for b in bars]; w=PIVOT_LEN
    piv=[(None,None)]*n
    for bi in range(2*w,n):
        center=bi-w; ch=highs[center]; cl=lows[center]
        ph=ch if (all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1])) else None
        pl=cl if (all(cl<x for x in lows[bi-2*w:center])  and all(cl<x for x in lows[center+1:bi+1]))  else None
        piv[bi]=(ph,pl)
    return piv

def run(bars, piv, smoothPct, gapClose, slPts, tpPts):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    trades=[]  # (pnl, reason)
    for bi in range(n):
        h,l,c = bars[bi]
        phVal,plVal = piv[bi]
        if phVal is not None:
            thr=smoothPct/100.0*c
            if resistance is None or abs(phVal-resistance)>=thr: resistance=phVal
        if plVal is not None:
            thr=smoothPct/100.0*c
            if support is None or abs(plVal-support)>=thr: support=plVal
        resValid=resistance is not None; supValid=support is not None
        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH    if supValid else None
        srGap=abs(resistance-support) if (resValid and supValid) else None

        # manage open trade — SL first (intrabar), then TP, then gap. No session flatten.
        if inTrade:
            exited=False
            if tradeDir==1 and l<=entry-slPts:
                trades.append((-slPts,"SL")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; exited=True
            elif tradeDir==-1 and h>=entry+slPts:
                trades.append((-slPts,"SL")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; exited=True
            if not exited and tpPts>0:
                if tradeDir==1 and h>=entry+tpPts:
                    trades.append((tpPts,"TP")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; exited=True
                elif tradeDir==-1 and l<=entry-tpPts:
                    trades.append((tpPts,"TP")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; exited=True
            if not exited and srGap is not None and srGap<=gapClose:
                trades.append(((c-entry) if tradeDir==1 else (entry-c),"GAP")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN

        if cooldown>0 and not inTrade: cooldown-=1
        wideEnough = srGap is not None and srGap>gapClose
        if (not inTrade) and cooldown==0 and wideEnough:   # no session gate
            if resValid and h>resZoneTop:   inTrade=True; tradeDir=1;  entry=c
            elif supValid and l<supZoneBot: inTrade=True; tradeDir=-1; entry=c
    return trades

def stats(trs):
    pnls=[t[0]-SLIP for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,win=0,pf=0,mdd=0,big=0,byr={})
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    r=0.0;peak=0.0;mdd=0.0
    for x in pnls: r+=x;peak=max(peak,r);mdd=max(mdd,peak-r)
    byr={}
    for t in trs: byr[t[1]]=byr.get(t[1],0)+1
    return dict(n=n,pnl=round(pnl),win=round(w/n*100,1),pf=round(gp/gl,2) if gl>0 else 999,mdd=round(mdd),big=round(min(pnls)),byr=byr)

CFGS=[
    ("winner  smooth1.0 gap40 sl300 +TP100 noSess", 1.0,40,300,100),
    ("default smooth1.0 gap70 sl200 +TP100 noSess", 1.0,70,200,100),
    ("winner  smooth1.0 gap40 sl300  noTP  noSess", 1.0,40,300,0),   # reference: same but no TP
]

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}\n")
    for name,sm,gp,sl,tp in CFGS:
        s=stats(run(bars,piv,sm,gp,sl,tp))
        ys=[stats(run(yr_bars[yr],yr_piv[yr],sm,gp,sl,tp))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name}")
        print(f"   pnl={s['pnl']:7} win{s['win']:5}% n{s['n']:5} pf{s['pf']:.2f} mdd{s['mdd']:6} bigLoss{s['big']} | {pos}/6 | {s['byr']}")
        print(f"   per-year: {[round(y) for y in ys]}")
        print()
