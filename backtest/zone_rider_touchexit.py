#!/usr/bin/env python3
"""
Zone Rider + touch-level exit test.

Entry: unchanged (break of outer zone edge; long above resistance+width, short below support-width).
Exits (whichever first):
  1. TOUCH-LEVEL: LONG exits when high >= support+zoneWidth (upper support band);
                 SHORT exits when low <= resistance-zoneWidth (lower resistance band).
  2. TP = 150 pts
  3. GAP convergence: |resistance - support| <= gapClose
  4. SL = 200 pts
NO session blocks (removed). smooth 1.0, gap 40.
Tested with and without the opposite-after-win filter.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0
PIVOT_LEN = 10
ZONE_WIDTH = 25.0
COOLDOWN = 20
SMOOTH = 1.0
GAP = 40.0
SL = 200.0
TP = 150.0

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((h,l,c)); yrs.append(dt.year)   # no session minute — sessions removed
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

def run(bars, piv, oppAfterWin):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0; blockDir=0
    trades=[]  # (pnl, reason)

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
        supZoneTop=support+ZONE_WIDTH    if supValid else None    # upper support band (LONG exit)
        resZoneBot=resistance-ZONE_WIDTH if resValid else None    # lower resistance band (SHORT exit)
        srGap=abs(resistance-support) if (resValid and supValid) else None

        if inTrade:
            exited=False
            # SL first (intrabar)
            if tradeDir==1 and l<=entry-SL:
                trades.append((-SL,"SL")); exited=True
            elif tradeDir==-1 and h>=entry+SL:
                trades.append((-SL,"SL")); exited=True
            # TP
            if not exited and TP>0:
                if tradeDir==1 and h>=entry+TP: trades.append((TP,"TP")); exited=True
                elif tradeDir==-1 and l<=entry-TP: trades.append((TP,"TP")); exited=True
            # touch-level (mean-reversion target)
            if not exited:
                if tradeDir==1 and supValid and h>=supZoneTop:
                    trades.append((supZoneTop-entry,"TOUCH")); exited=True
                elif tradeDir==-1 and resValid and l<=resZoneBot:
                    trades.append((entry-resZoneBot,"TOUCH")); exited=True
            # gap convergence
            if not exited and srGap is not None and srGap<=GAP:
                trades.append(((c-entry) if tradeDir==1 else (entry-c),"GAP")); exited=True
            if exited:
                pnl=trades[-1][0]
                inTrade=False; d=tradeDir; tradeDir=0; entry=None; cooldown=COOLDOWN
                if oppAfterWin: blockDir = d if pnl>0 else 0

        if cooldown>0 and not inTrade: cooldown-=1
        wideEnough = srGap is not None and srGap>GAP
        if (not inTrade) and cooldown==0 and wideEnough:
            longOK  = blockDir != 1
            shortOK = blockDir != -1
            if resValid and h>resZoneTop and longOK:
                inTrade=True; tradeDir=1; entry=c; blockDir=0
            elif supValid and l<supZoneBot and shortOK:
                inTrade=True; tradeDir=-1; entry=c; blockDir=0
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

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}")
    print("config: smooth1.0 gap40 sl200 tp150 + touch-level exit, NO sessions\n")
    for name,opp in [("touch-exit, NO opp-win filter",False),
                     ("touch-exit + opposite-after-win",True)]:
        s=stats(run(bars,piv,opp))
        ys=[stats(run(yr_bars[yr],yr_piv[yr],opp))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name}")
        print(f"   pnl={s['pnl']:7} win{s['win']:5}% n{s['n']:5} pf{s['pf']:.2f} mdd{s['mdd']:6} bigLoss{s['big']} | {pos}/6 | {s['byr']}")
        print(f"   per-year: {[round(y) for y in ys]}\n")
