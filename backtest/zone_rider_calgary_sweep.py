#!/usr/bin/env python3
"""
Parameter sweep for Zone Rider "Calgary" (break entry + gap-convergence exit).
Sweeps smoothSRPct x gapClosePts x slPts, reports 5yr pnl/pf/n + profitable-year
count (to catch configs that win big in one year but aren't robust).

Reuses the faithful Calgary port logic (parameterized).
"""
import csv, sys
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0
PIVOT_LEN = 10
ZONE_WIDTH = 25.0
COOLDOWN = 20

def blocked(m): return (120<=m<150) or (450<=m<540) or (1020<=m<1050)
def is_eod(m):  return 900<=m<960

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars,yrs

def precompute_pivots(bars):
    """Pivots don't depend on the swept params, so compute newPH/newPL once."""
    n=len(bars); highs=[b[0] for b in bars]; lows=[b[1] for b in bars]; w=PIVOT_LEN
    piv=[(None,None)]*n
    for bi in range(2*w, n):
        center=bi-w; ch=highs[center]; cl=lows[center]
        ph = ch if (all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1])) else None
        pl = cl if (all(cl<x for x in lows[bi-2*w:center])  and all(cl<x for x in lows[center+1:bi+1]))  else None
        piv[bi]=(ph,pl)
    return piv

def run(bars, piv, smoothPct, gapClose, slPts):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    trades=[]
    for bi in range(n):
        h,l,c,m = bars[bi]
        eod=is_eod(m); inBlk=blocked(m)
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

        if inTrade and (eod or inBlk):
            trades.append((c-entry) if tradeDir==1 else (entry-c)); inTrade=False; tradeDir=0; entry=None; cooldown=0
        if inTrade:
            if tradeDir==1 and l<=entry-slPts:
                trades.append(-slPts); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
            elif tradeDir==-1 and h>=entry+slPts:
                trades.append(-slPts); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
        if inTrade and srGap is not None and srGap<=gapClose:
            trades.append((c-entry) if tradeDir==1 else (entry-c)); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
        if cooldown>0 and not inTrade: cooldown-=1
        wideEnough = srGap is not None and srGap>gapClose
        if (not inTrade) and (not eod) and (not inBlk) and cooldown==0 and wideEnough:
            if resValid and h>resZoneTop:   inTrade=True; tradeDir=1;  entry=c
            elif supValid and l<supZoneBot: inTrade=True; tradeDir=-1; entry=c
    return trades

def stat(trs):
    pnls=[t-SLIP for t in trs]; n=len(pnls)
    if n==0: return 0,0,0.0
    pnl=sum(pnls); gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    return round(pnl), n, (round(gp/gl,2) if gl>0 else 999)

if __name__=="__main__":
    print("loading + precomputing pivots…"); bars,yrs=load()
    piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx_by_year={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    # precompute per-year slices + their pivots ONCE (not per param combo)
    yr_bars={yr:[bars[i] for i in idx_by_year[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}\n")

    SMOOTH=[0.30,0.50,1.00]
    GAP=[40,70,100]
    SL=[100,200,300]
    print(f"{'smooth':>6} {'gap':>4} {'sl':>4} | {'pnl':>7} {'n':>5} {'pf':>5} | +yrs | per-year pnl")
    results=[]
    for sm in SMOOTH:
        for gp in GAP:
            for sl in SL:
                full_pnl,full_n,full_pf = stat(run(bars,piv,sm,gp,sl))
                ys=[]
                for yr in years:
                    p,_,_=stat(run(yr_bars[yr],yr_piv[yr],sm,gp,sl)); ys.append(p)
                pos=sum(1 for y in ys if y>0)
                results.append((full_pnl,full_pf,pos,sm,gp,sl,ys))
                print(f"{sm:>6} {gp:>4} {sl:>4} | {full_pnl:>7} {full_n:>5} {full_pf:>5} | {pos}/6  | {[round(y) for y in ys]}")
    print("\n=== top 5 by 5yr pnl (with robustness) ===")
    for full_pnl,full_pf,pos,sm,gp,sl,ys in sorted(results,reverse=True)[:5]:
        print(f"smooth={sm} gap={gp} sl={sl}: pnl={full_pnl} pf={full_pf} +yrs={pos}/6")
