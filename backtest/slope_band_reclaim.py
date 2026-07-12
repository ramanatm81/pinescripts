#!/usr/bin/env python3
"""
NEW STRATEGY — "Deep-fade band reclaim" v2 (per user 2026-07-11).
Retains the CORE of slope_strategy: continuous rolling slope (doji/EOD-aware) and the
fractal S/R zone (ta.pivotlow/high, srHalfWidth=10 => 21-bar pivots, srZoneWidth=25).

LONG-only fade. Enter when ALL true:
  1. VWAP -2sigma support band is DECREASING     (lo < lo[lbBand])
  2. slope deep-negative, computed continuously exactly like the base:
        legSlope <= -deepSlope
  3. price pierced BELOW the -2sigma band by >= minPierce, then RECLAIMED it (close > lo)
  4. entry is OUTSIDE the base's S/R zones     (not srBlock: not near fractal high OR low)
Exit: existing MFE trail (arm +trailTrigger, trail trailDist/Strong) + HARD SL 200 pts. EOD flat.

Standalone — does NOT touch backtest.py or the validated slope base.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
from collections import Counter

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
KSIGMA=2.0

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

def run(bars, vol, bands, p):
    lookback   = p.get("lookback",10)
    deepSlope  = p["deepSlope"]
    lbBand     = p["lbBand"]
    slPts      = p.get("slPts",200.0)
    trailTrig  = p.get("trailTrigger",30.0)
    trailDist  = p.get("trailDist",8.0)
    trailStrong= p.get("trailDistStrong",10.0)
    cooldown   = p.get("cooldownBars",10)
    minPierce  = p.get("minPierce",0.0)
    exitMode   = p.get("exitMode","trail")  # "trail" | "pivotHi" | "vwapUp"
    # --- base S/R fractal params (match validated slope base) ---
    enableSRFilter = p.get("enableSRFilter",True)
    srHalfWidth    = p.get("srHalfWidth",10)
    srZoneWidth    = p.get("srZoneWidth",25.0)
    dojiPct        = p.get("dojiPct",0.0)   # base default: no doji skip unless set

    highs=[b[2] for b in bars]; lows=[b[3] for b in bars]
    trades=[]; slopeBuf=[]
    inTrade=False; entryPrice=None; bestPrice=None; trailStop=None
    cd=0; heat=None
    armed=False
    lastFractalHigh=None; lastFractalLow=None
    lastFractalHighBar=None; lastFractalLowBar=None
    prevDate=None

    for bi,((dt,o,h,l,c,m),v) in enumerate(zip(bars,vol)):
        mean,up,lo,w = bands[bi]
        newDay = dt.date()!=prevDate; prevDate=dt.date()
        isRTH = 570 <= m < 1020

        # ---- doji flag (base uses body% < dojiPct to skip slope update); default off ----
        rng=h-l; body=abs(c-o)
        isDoji = (dojiPct>0.0) and rng>0 and (body/rng)<dojiPct
        eodClose = newDay  # base clears slope buffer at session boundary; approximate with new-day

        # ---- fractal pivots (identical to base) ----
        wf=srHalfWidth
        if bi >= 2*wf:
            center = bi-wf
            ch=highs[center]
            left=highs[bi-2*wf:center]; right=highs[center+1:bi+1]
            if all(ch>x for x in left) and all(ch>x for x in right):
                lastFractalHigh=ch; lastFractalHighBar=center
            cl=lows[center]
            left=lows[bi-2*wf:center]; right=lows[center+1:bi+1]
            if all(cl<x for x in left) and all(cl<x for x in right):
                lastFractalLow=cl; lastFractalLowBar=center

        nearHigh = (lastFractalHigh is not None) and abs(c-lastFractalHigh)<=srZoneWidth
        nearLow  = (lastFractalLow  is not None) and abs(c-lastFractalLow) <=srZoneWidth
        srBlock  = enableSRFilter and (nearHigh or nearLow)

        # ---- rolling slope (continuous, doji/EOD-aware — identical to base) ----
        if not eodClose and not isDoji:
            slopeBuf.append(c)
            if len(slopeBuf)>lookback: slopeBuf.pop(0)
        if eodClose: slopeBuf=[c]  # reset buffer at new session like base anchor reset
        legSlope=None
        if len(slopeBuf)==lookback:
            n=lookback; sx=sy=sxy=sxx=0.0
            for i in range(n):
                x=float(i); y=slopeBuf[i]; sx+=x; sy+=y; sxy+=x*y; sxx+=x*x
            denom=n*sxx-sx*sx
            legSlope=round((n*sxy-sx*sy)/denom,2) if denom!=0 else 0.0

        # ---- EOD flat ----
        if inTrade and newDay:
            trades.append((1,entryPrice,c,c-entryPrice,"EOD",dt,heat))
            inTrade=False; trailStop=None; bestPrice=None; cd=0; armed=False

        if cd>0 and not inTrade: cd-=1

        # ---- band falling? ----
        bandFalling=False
        if bi>=lbBand and w>=1.0:
            bandFalling = lo < bands[bi-lbBand][2]

        # ---- pierce/arm ----
        if w>=1.0 and l <= lo and (lo-l) >= minPierce:
            armed=True

        # ---- manage open trade ----
        if inTrade:
            heat = min(heat, l-entryPrice) if heat is not None else (l-entryPrice)
            if l <= entryPrice-slPts:
                fill=entryPrice-slPts
                trades.append((1,entryPrice,fill,fill-entryPrice,"SL",dt,heat))
                inTrade=False; trailStop=None; bestPrice=None; cd=cooldown; armed=False
            else:
                bestPrice = h if bestPrice is None else max(bestPrice,h)
                if bestPrice-entryPrice >= trailTrig:
                    ad = trailStrong if (legSlope is not None and legSlope <= -deepSlope) else trailDist
                    ts = bestPrice-ad
                    trailStop = ts if trailStop is None else max(trailStop,ts)
                if trailStop is not None and l <= trailStop:
                    trades.append((1,entryPrice,trailStop,trailStop-entryPrice,"TRAIL",dt,heat))
                    inTrade=False; trailStop=None; bestPrice=None; cd=cooldown; armed=False

        # ---- ENTRY: reclaim + band falling + deep-neg slope + OUTSIDE S/R zone ----
        if (not inTrade and cd==0 and armed and w>=1.0 and isRTH
                and c > lo and bandFalling and not srBlock
                and legSlope is not None and legSlope <= -deepSlope):
            inTrade=True; entryPrice=c; bestPrice=None; trailStop=None; heat=0.0; armed=False

    return trades

def summ(trs, slip, years):
    p=[t[3]-slip for t in trs]; n=len(p)
    if n==0: return (0,0,0,0,[0]*len(years),0,0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    yl=[]; pos=0
    for y in years:
        yy=round(sum(t[3]-slip for t in trs if t[5].year==y))
        if yy>0: pos+=1
        yl.append(yy)
    avgHeat=round(sum(t[6] for t in trs)/n,1)
    return (round(sum(p)), n, round(gp/gl,2) if gl>0 else 999, round(100*w/n,1), yl, pos, avgHeat)

if __name__=="__main__":
    print("loading + VWAP bands…"); bars,vol=load(); bands=vwap_bands(bars,vol)
    years=[2021,2022,2023,2024,2025,2026]
    print(f"bars {len(bars):,}")
    BASE=dict(lookback=10, lbBand=10, slPts=200.0, trailTrigger=30.0, trailDist=8.0,
              trailDistStrong=10.0, cooldownBars=10,
              enableSRFilter=True, srHalfWidth=10, srZoneWidth=25.0)

    print("\n===== deep-slope x pierce-depth  (SL=200, S/R zone filter ON, trail) =====")
    for slip in (0.0,1.0):
        print(f"\n-- slip {slip} --  {'deep/minP':>10} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'heat':>6} | +yr | per-year")
        for ds in (5,7,9):
            for mp in (0,10,15):
                trs=run(bars,vol,bands,dict(BASE,deepSlope=ds,minPierce=float(mp)))
                pnl,n,pf,win,yl,pos,heat=summ(trs,slip,years)
                print(f"     d{ds} p{mp:>2} | {pnl:>7} {n:>5} {pf:>5} {win:>5} {heat:>6} | {pos}/6 | {yl}")
    trs=run(bars,vol,bands,dict(BASE,deepSlope=7,minPierce=10.0))
    print("\ndeep7/minPierce10 exit mix:", dict(Counter(t[4] for t in trs)))

    print("\n===== SL sweep at best signal (deep7, minPierce10, S/R filter ON) =====")
    for slip in (0.0,1.0):
        print(f"-- slip {slip} --  {'SL':>4} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} | +yr | per-year")
        for sl in (30,40,50,75,100,150,200):
            trs=run(bars,vol,bands,dict(BASE,deepSlope=7,minPierce=10.0,slPts=float(sl)))
            pnl,n,pf,win,yl,pos,heat=summ(trs,slip,years)
            print(f"            {sl:>4} | {pnl:>7} {n:>5} {pf:>5} {win:>5} | {pos}/6 | {yl}")
