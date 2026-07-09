#!/usr/bin/env python3
"""
Robustness sweep for the Rule 1 winner (breach-follow entry + trailing-floor exit).
Sweeps breachBars x SL x smoothSRPct around the winner (5 / 200 / 1.0). Reports 5yr
pnl/pf/n + profitable-year count so we can see if the edge is a stable plateau or a spike.
No TP, no gap, no sessions, no opp-win filter. 1pt slip.
"""
import csv
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

def run(bars, piv, smoothPct, slPts, breachBars):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    upB=0; dnB=0
    trades=[]
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
            if tradeDir==1 and l<=entry-slPts: trades.append(-slPts); exited=True
            elif tradeDir==-1 and h>=entry+slPts: trades.append(-slPts); exited=True
            if not exited:
                if tradeDir==1 and supValid and l<=supZoneTop: trades.append(supZoneTop-entry); exited=True
                elif tradeDir==-1 and resValid and h>=resZoneBot: trades.append(entry-resZoneBot); exited=True
            if exited: inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            if upB==breachBars: inTrade=True; tradeDir=1; entry=c
            elif dnB==breachBars: inTrade=True; tradeDir=-1; entry=c
    return trades

def stat(trs):
    pnls=[t-SLIP for t in trs]; n=len(pnls)
    if n==0: return 0,0,0.0
    pnl=sum(pnls); gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    return round(pnl), n, (round(gp/gl,2) if gl>0 else 999)

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}\n")
    SMOOTH=[0.5,1.0,1.5]; SL=[100,200,300]; BR=[3,5,8]
    print(f"{'smooth':>6} {'sl':>4} {'br':>3} | {'pnl':>7} {'n':>5} {'pf':>5} | +yrs")
    results=[]
    for sm in SMOOTH:
        for sl in SL:
            for br in BR:
                fp,fn,fpf = stat(run(bars,piv,sm,sl,br))
                ys=[stat(run(yr_bars[yr],yr_piv[yr],sm,sl,br))[0] for yr in years]
                pos=sum(1 for y in ys if y>0)
                results.append((fp,fpf,pos,sm,sl,br))
                print(f"{sm:>6} {sl:>4} {br:>3} | {fp:>7} {fn:>5} {fpf:>5} | {pos}/6")
    print("\n=== top 8 by pnl ===")
    for fp,fpf,pos,sm,sl,br in sorted(results,reverse=True)[:8]:
        print(f"smooth={sm} sl={sl} breachBars={br}: pnl={fp} pf={fpf} +yrs={pos}/6")
    print("\n=== worst 3 (stability check) ===")
    for fp,fpf,pos,sm,sl,br in sorted(results)[:3]:
        print(f"smooth={sm} sl={sl} breachBars={br}: pnl={fp} pf={fpf} +yrs={pos}/6")
