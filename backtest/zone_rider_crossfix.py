#!/usr/bin/env python3
"""
Fix the crossed-band inversion in Zone Rider (proven on 2026-07-10 London seq269:
support 29962 > resistance 29706 by 255pts -> upBreachBars free-ran to 1090, entered
LONG on flat drift, flushed 1 bar later by the inverted floor supZoneTop=29987).

Base = shipped Boulder logic (breach-hold entry, SL->MFE-trail->floor exit).

FIX (crossed = support >= resistance):
  * Entry: ignore the (free-running) breach counters. Pick direction by NEARER raw level
    (|close-support| vs |close-resistance|). Nearer support -> SHORT, nearer resistance
    -> LONG. Still require a HELD breach beyond that side's OUTER band for breachBars,
    so it can't fire on flat drift.
  * Floor exit: the trailing-floor geometry is inverted while crossed, so DISABLE it and
    rely on SL + MFE-trail (both direction-correct). Uncrossed = unchanged.

Compare: BOULDER (broken) vs CROSSFIX, full 5yr + per-year, + removed/changed-trade W/L.
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
MFE_TRAIL = 80.0

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

def run(bars, piv, crossfix):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    upB=0; dnB=0
    mfe=0.0; peak=None
    trades=[]  # (dir, pnl, crossedAtEntry, reason)
    entryCrossed=False
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
        crossed = resValid and supValid and support >= resistance

        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH    if supValid else None
        supZoneTop=support+ZONE_WIDTH    if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None

        # Breach counters: when crossfix + crossed, count breaches against the NEARER
        # raw level's outer band instead of the fixed long=res/short=sup mapping.
        if crossfix and crossed:
            dSup=abs(c-support); dRes=abs(c-resistance)
            # nearer resistance -> long side; nearer support -> short side
            longSideBand  = resZoneTop            # break UP above res band
            shortSideBand = supZoneBot            # break DOWN below sup band
            upB = upB+1 if (dRes<dSup and h>longSideBand)  else 0
            dnB = dnB+1 if (dSup<dRes and l<shortSideBand) else 0
        else:
            upB = upB+1 if (resValid and h>resZoneTop) else 0
            dnB = dnB+1 if (supValid and l<supZoneBot) else 0

        exited=False
        if inTrade:
            if tradeDir==1:
                if h-entry>mfe: mfe=h-entry
                peak=max(peak,h)
            else:
                if entry-l>mfe: mfe=entry-l
                peak=min(peak,l)
            # 1) SL
            if tradeDir==1 and l<=entry-SL: trades.append((1,-SL,entryCrossed,"SL")); exited=True
            elif tradeDir==-1 and h>=entry+SL: trades.append((-1,-SL,entryCrossed,"SL")); exited=True
            # 2) MFE trail
            if not exited and mfe>=MFE_TRIG:
                if tradeDir==1 and l<=peak-MFE_TRAIL: trades.append((1,(peak-MFE_TRAIL)-entry,entryCrossed,"MFE")); exited=True
                elif tradeDir==-1 and h>=peak+MFE_TRAIL: trades.append((-1,entry-(peak+MFE_TRAIL),entryCrossed,"MFE")); exited=True
            # 3) trailing floor — DISABLED while crossed under crossfix (inverted geometry)
            floorOK = not (crossfix and entryCrossed)
            if not exited and floorOK:
                if tradeDir==1 and supValid and l<=supZoneTop: trades.append((1,supZoneTop-entry,entryCrossed,"FLR")); exited=True
                elif tradeDir==-1 and resValid and h>=resZoneBot: trades.append((-1,entry-resZoneBot,entryCrossed,"FLR")); exited=True
            if exited:
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None

        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            if upB==BREACH_BARS:
                inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c; entryCrossed=crossed
            elif dnB==BREACH_BARS:
                inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c; entryCrossed=crossed
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

    print(f"{'config':22} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yrs | per-year")
    for name,cf in [("BOULDER (broken)",False),("CROSSFIX",True)]:
        s=stat(run(bars,piv,cf))
        ys=[stat(run(yr_bars[yr],yr_piv[yr],cf))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name:22} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {[round(y) for y in ys]}")

    # crossed-trade breakdown under each
    print("\n=== crossed-entry trades only ===")
    for name,cf in [("BOULDER (broken)",False),("CROSSFIX",True)]:
        trs=[t for t in run(bars,piv,cf) if t[2]]
        s=stat(trs); dirs={1:0,-1:0}
        for t in trs: dirs[t[0]]+=1
        print(f"  {name:20} n={s['n']:>4} pnl={s['pnl']:>6} pf={s['pf']:>4} win={s['win']:>5} | long={dirs[1]} short={dirs[-1]}")
