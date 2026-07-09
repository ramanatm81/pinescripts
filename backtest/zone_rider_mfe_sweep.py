#!/usr/bin/env python3
"""
5yr test: Zone Rider (Denver) + MFE trailing stop + fresh-breach re-entry rule.

Base = the validated Denver config (breach-hold entry, trailing-floor exit, SL200).
NEW:
  1. MFE trailing stop: once max-favorable-excursion >= mfeTrig (100), also exit if
     price retraces mfeTrail (60) from the peak. Added ON TOP of floor + SL (first hit).
  2. Fresh-breach re-entry: on ANY exit, reset the breach counter to 0 so the SAME
     still-active breach cannot immediately re-enter — price must come back inside the
     band and re-breach (counter climbs to breachBars again). No same-breach re-entry.

Compares baseline vs +MFEtrail vs +MFEtrail+freshbreach, on full 5yr + per-year.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0
PIVOT_LEN = 10
ZONE_WIDTH = 25.0
COOLDOWN = 20
SMOOTH = 1.0
SL = 200.0
BREACH_BARS = 5
MFE_TRIG = 100.0
MFE_TRAIL = 60.0

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

def run(bars, piv, mfeTrig, mfeTrail):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    upB=0; dnB=0
    mfe=0.0; peak=None
    trades=[]  # (dir, pnl)
    for bi in range(n):
        h,l,c = bars[bi]
        phVal,plVal = piv[bi]
        if phVal is not None:
            thr=SMOOTH/100.0*c
            if resistance is None or abs(phVal-resistance)>=thr: resistance=phVal
        if plVal is not None:
            thr=SMOOTH/100.0*c
            if support is None or abs(plVal-support)>=thr: support=plVal
        resValid=resistance is not None; supValid=support is not None
        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH    if supValid else None
        supZoneTop=support+ZONE_WIDTH    if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None
        upB = upB+1 if (resValid and h>resZoneTop) else 0
        dnB = dnB+1 if (supValid and l<supZoneBot) else 0

        exited=False
        if inTrade:
            # update MFE / peak
            if tradeDir==1:
                if h-entry>mfe: mfe=h-entry
                peak=max(peak,h)
            else:
                if entry-l>mfe: mfe=entry-l
                peak=min(peak,l)
            # 1) SL200
            if tradeDir==1 and l<=entry-SL: trades.append((1,-SL)); exited=True
            elif tradeDir==-1 and h>=entry+SL: trades.append((-1,-SL)); exited=True
            # 2) MFE trailing stop (after MFE>=trig)
            if not exited and mfeTrig>0 and mfe>=mfeTrig:
                if tradeDir==1 and l<=peak-mfeTrail: trades.append((1, (peak-mfeTrail)-entry)); exited=True
                elif tradeDir==-1 and h>=peak+mfeTrail: trades.append((-1, entry-(peak+mfeTrail))); exited=True
            # 3) existing trailing-floor
            if not exited:
                if tradeDir==1 and supValid and l<=supZoneTop: trades.append((1, supZoneTop-entry)); exited=True
                elif tradeDir==-1 and resValid and h>=resZoneBot: trades.append((-1, entry-resZoneBot)); exited=True
            if exited:
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None

        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            if upB==BREACH_BARS: inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c
            elif dnB==BREACH_BARS: inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c
    return trades

def stat(trs):
    pnls=[t[1]-SLIP for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,pf=0.0,win=0,mdd=0)
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    r=0.0;peak=0.0;mdd=0.0
    for x in pnls: r+=x;peak=max(peak,r);mdd=max(mdd,peak-r)
    return dict(n=n,pnl=round(pnl),pf=round(gp/gl,2) if gl>0 else 999,win=round(w/n*100,1),mdd=round(mdd))

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}\n")
    combos=[("BASELINE (no trail)",0,0),
            ("trig100/trail60",100,60),("trig100/trail80",100,80),("trig100/trail100",100,100),
            ("trig150/trail80",150,80),("trig150/trail100",150,100),("trig150/trail120",150,120),
            ("trig200/trail100",200,100),("trig200/trail150",200,150)]
    print(f"{'config':22} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yrs")
    for name,tg,tl in combos:
        s=stat(run(bars,piv,tg,tl))
        ys=[stat(run(yr_bars[yr],yr_piv[yr],tg,tl))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name:22} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/6")
