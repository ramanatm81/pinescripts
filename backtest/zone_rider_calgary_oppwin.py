#!/usr/bin/env python3
"""
Zone Rider "Calgary" + TP + opposite-after-win filter.

Config: smooth 1.0 / gap 40 / SL 100 / TP 150, sessions ON.
Filter: after a WINNING trade, the IMMEDIATE next entry must be the OPPOSITE
direction (blocks same-side once). After that one entry fires (win or lose), the
restriction lifts until the next win. A losing trade imposes no restriction.

Compares against the no-filter version of the same config so we can see the delta.
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
    n=len(bars); highs=[b[0] for b in bars]; lows=[b[1] for b in bars]; w=PIVOT_LEN
    piv=[(None,None)]*n
    for bi in range(2*w,n):
        center=bi-w; ch=highs[center]; cl=lows[center]
        ph=ch if (all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1])) else None
        pl=cl if (all(cl<x for x in lows[bi-2*w:center])  and all(cl<x for x in lows[center+1:bi+1]))  else None
        piv[bi]=(ph,pl)
    return piv

def run(bars, piv, smoothPct, gapClose, slPts, tpPts, oppAfterWin):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    blockDir=0   # if !=0, the next entry must NOT be this direction (opposite-after-win)
    trades=[]    # (pnl, reason)

    def close(pnl, reason, dir_):
        nonlocal inTrade,tradeDir,entry,cooldown,blockDir
        trades.append((pnl,reason))
        inTrade=False; tradeDir=0; entry=None
        cooldown = 0 if reason in ("BLK","EOD") else COOLDOWN
        # opposite-after-win: a WINNING trade blocks same-side on the immediate next entry
        if oppAfterWin:
            blockDir = dir_ if pnl>0 else 0   # win -> block that dir; loss -> clear

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

        # session/EOD flatten
        if inTrade and (eod or inBlk):
            close((c-entry) if tradeDir==1 else (entry-c), "BLK", tradeDir);
        # SL
        if inTrade:
            if tradeDir==1 and l<=entry-slPts: close(-slPts,"SL",1)
            elif tradeDir==-1 and h>=entry+slPts: close(-slPts,"SL",-1)
        # TP
        if inTrade and tpPts>0:
            if tradeDir==1 and h>=entry+tpPts: close(tpPts,"TP",1)
            elif tradeDir==-1 and l<=entry-tpPts: close(tpPts,"TP",-1)
        # gap convergence
        if inTrade and srGap is not None and srGap<=gapClose:
            close((c-entry) if tradeDir==1 else (entry-c), "GAP", tradeDir)

        if cooldown>0 and not inTrade: cooldown-=1
        wideEnough = srGap is not None and srGap>gapClose
        if (not inTrade) and (not eod) and (not inBlk) and cooldown==0 and wideEnough:
            longOK  = blockDir != 1
            shortOK = blockDir != -1
            if resValid and h>resZoneTop and longOK:
                inTrade=True; tradeDir=1; entry=c; blockDir=0   # entry consumes the restriction
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
    print(f"bars {len(bars):,}\n")
    print("config: smooth1.0 gap40 sl100 tp150, sessions ON\n")
    for name,opp in [("NO filter (baseline for this config)",False),
                     ("OPPOSITE-after-win filter",True)]:
        s=stats(run(bars,piv,1.0,40,100,150,opp))
        ys=[stats(run(yr_bars[yr],yr_piv[yr],1.0,40,100,150,opp))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name}")
        print(f"   pnl={s['pnl']:7} win{s['win']:5}% n{s['n']:5} pf{s['pf']:.2f} mdd{s['mdd']:6} bigLoss{s['big']} | {pos}/6 | {s['byr']}")
        print(f"   per-year: {[round(y) for y in ys]}\n")
