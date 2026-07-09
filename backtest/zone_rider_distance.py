#!/usr/bin/env python3
"""
Test the DISTANCE entry mode for Zone Rider (breach-follow + trailing-floor exit).

Distance mode: enter once price pushes breachDistPts BEYOND the outer band edge.
  LONG  when high >= resZoneTop + dist  (resistance+zoneWidth+dist)
  SHORT when low  <= supZoneBot - dist  (support-zoneWidth-dist)

Sweeps dist in {10,20,30} at smooth 1.0 and 1.5, SL 200. Compares to the validated
bars-held baseline (breachBars=5). Reports 5yr pnl/pf/n + per-year + long/short.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0
PIVOT_LEN = 10
ZONE_WIDTH = 25.0
COOLDOWN = 20
SL = 200.0
BREACH_BARS = 5

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((h,l,c)); yrs.append(dt.year)
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

def run(bars, piv, smoothPct, mode, dist):
    """mode: 'bars' or 'dist'. dist used only when mode=='dist'."""
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    upB=0; dnB=0
    trades=[]  # (pnl, dir)
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
        supZoneTop=support+ZONE_WIDTH    if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None
        upB = upB+1 if (resValid and h>resZoneTop) else 0
        dnB = dnB+1 if (supValid and l<supZoneBot) else 0

        if inTrade:
            exited=False
            if tradeDir==1 and l<=entry-SL: trades.append((-SL,1)); exited=True
            elif tradeDir==-1 and h>=entry+SL: trades.append((-SL,-1)); exited=True
            if not exited:
                if tradeDir==1 and supValid and l<=supZoneTop: trades.append((supZoneTop-entry,1)); exited=True
                elif tradeDir==-1 and resValid and h>=resZoneBot: trades.append((entry-resZoneBot,-1)); exited=True
            if exited: inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
        if cooldown>0 and not inTrade: cooldown-=1

        if (not inTrade) and cooldown==0:
            if mode=='dist':
                longTrig  = resValid and h >= resZoneTop + dist
                shortTrig = supValid and l <= supZoneBot - dist
            else:
                longTrig  = upB==BREACH_BARS
                shortTrig = dnB==BREACH_BARS
            if longTrig: inTrade=True; tradeDir=1; entry=c
            elif shortTrig: inTrade=True; tradeDir=-1; entry=c
    return trades

def stat(trs, side=None):
    if side is not None: trs=[t for t in trs if t[1]==side]
    pnls=[t[0]-SLIP for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,pf=0.0,win=0)
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    return dict(n=n,pnl=round(pnl),pf=round(gp/gl,2) if gl>0 else 999,win=round(w/n*100,1))

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}\n")

    configs=[("BARS held=5 (baseline)",1.0,'bars',0),
             ("DIST=10",1.0,'dist',10),("DIST=20",1.0,'dist',20),("DIST=30",1.0,'dist',30),
             ("smooth1.5 BARS held=5",1.5,'bars',0),
             ("smooth1.5 DIST=10",1.5,'dist',10),("smooth1.5 DIST=20",1.5,'dist',20),("smooth1.5 DIST=30",1.5,'dist',30)]
    print(f"{'config':28} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} | +yrs | L pnl / S pnl | per-year")
    for name,sm,mode,d in configs:
        trs=run(bars,piv,sm,mode,d); s=stat(trs); L=stat(trs,1); S=stat(trs,-1)
        ys=[stat(run(yr_bars[yr],yr_piv[yr],sm,mode,d))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name:28} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} | {pos}/6  | {L['pnl']:>6}/{S['pnl']:>6} | {[round(y) for y in ys]}")
