#!/usr/bin/env python3
"""
5yr test of Zone Rider build "Calgary" (zone_rider.pine, current break-out/gap version).

Faithful port of the current .pine logic:
  - Smoothed S/R: support/resistance are ta.pivotlow/high, but only STEP when a new
    pivot differs by >= smoothSRPct% of price; otherwise hold flat.
  - Zone edges: level +/- zoneWidth.
  - ENTRY (momentum break): high > resistance+zoneWidth -> LONG ; low < support-zoneWidth -> SHORT.
    Gated: not in trade, cooldown==0, session OK, channel |res-sup| > gapClosePts (wideEnough).
  - EXIT: |resistance - support| <= gapClosePts (convergence), any bar. Hard SL backstop.
  - cooldownBars idle after exit.

Bar-close fill model. PnL in points. 1pt slip applied in stats.
"""
import csv, sys
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0

# config = current .pine defaults (Calgary)
PIVOT_LEN   = 10
ZONE_WIDTH  = 25.0
MAX_PIV_AGE = 0
SMOOTH_PCT  = 1.00
GAP_CLOSE   = 70.0
COOLDOWN    = 20
USE_SL      = True
SL_PTS      = 200.0
EN_LONG     = True
EN_SHORT    = True

def blocked(m):  # LN, preNY, ETH on; NYopen off — mirrors .pine defaults
    return (120 <= m < 150) or (450 <= m < 540) or (1020 <= m < 1050)
def is_eod(m):
    return 900 <= m < 960

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars,yrs

def run(bars):
    n=len(bars); highs=[]; lows=[]
    resistance=None; support=None; resBar=None; supBar=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    trades=[]  # (dir, entry, exit, pnl, reason)
    pos_prev_flat=True  # emulate broker next-bar behaviour loosely

    for bi in range(n):
        h,l,c,m = bars[bi]; highs.append(h); lows.append(l)
        eod=is_eod(m); inBlk=blocked(m)

        # ---- pivots (confirmed pivotLen bars back) ----
        w=PIVOT_LEN
        newPH=newPL=False; phVal=plVal=None
        if bi>=2*w:
            center=bi-w; ch=highs[center]
            if all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1]):
                newPH=True; phVal=ch
            cl=lows[center]
            if all(cl<x for x in lows[bi-2*w:center]) and all(cl<x for x in lows[center+1:bi+1]):
                newPL=True; plVal=cl

        # ---- smoothed level step ----
        if newPH:
            thr=SMOOTH_PCT/100.0*c
            if resistance is None or abs(phVal-resistance)>=thr:
                resistance=phVal; resBar=bi-w
        if newPL:
            thr=SMOOTH_PCT/100.0*c
            if support is None or abs(plVal-support)>=thr:
                support=plVal; supBar=bi-w

        resValid = resistance is not None and (MAX_PIV_AGE==0 or (resBar is not None and bi-resBar<=MAX_PIV_AGE))
        supValid = support    is not None and (MAX_PIV_AGE==0 or (supBar is not None and bi-supBar<=MAX_PIV_AGE))
        resZoneTop = resistance+ZONE_WIDTH if resValid else None
        supZoneBot = support-ZONE_WIDTH    if supValid else None
        srGap = abs(resistance-support) if (resValid and supValid) else None

        # ---- EOD / session flatten ----
        if inTrade and (eod or inBlk):
            trades.append((tradeDir, entry, c, (c-entry) if tradeDir==1 else (entry-c), "BLK"))
            inTrade=False; tradeDir=0; entry=None; cooldown=0

        # ---- hard SL (intrabar) ----
        if inTrade and USE_SL:
            if tradeDir==1 and l <= entry-SL_PTS:
                trades.append((1, entry, entry-SL_PTS, -SL_PTS, "SL")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
            elif tradeDir==-1 and h >= entry+SL_PTS:
                trades.append((-1, entry, entry+SL_PTS, -SL_PTS, "SL")); inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN

        # ---- gap-convergence exit ----
        if inTrade and srGap is not None and srGap <= GAP_CLOSE:
            trades.append((tradeDir, entry, c, (c-entry) if tradeDir==1 else (entry-c), "GAP"))
            inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN

        # ---- cooldown tick ----
        if cooldown>0 and not inTrade: cooldown-=1

        # ---- entry (break of outer zone edge) ----
        wideEnough = srGap is not None and srGap > GAP_CLOSE
        canEnter = (not inTrade) and (not eod) and (not inBlk) and cooldown==0 and wideEnough
        if canEnter:
            breakUp   = resValid and h > resZoneTop
            breakDown = supValid and l < supZoneBot
            if EN_LONG and breakUp:
                inTrade=True; tradeDir=1; entry=c
            elif EN_SHORT and breakDown:
                inTrade=True; tradeDir=-1; entry=c

    return trades

def stats(trs):
    pnls=[t[3]-SLIP for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,win=0,pf=0,mdd=0,big=0,byreason={})
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    r=0.0;peak=0.0;mdd=0.0
    for x in pnls: r+=x;peak=max(peak,r);mdd=max(mdd,peak-r)
    byr={}
    for t in trs:
        byr[t[4]]=byr.get(t[4],0)+1
    return dict(n=n,pnl=round(pnl),win=round(w/n*100,1),pf=round(gp/gl,2) if gl>0 else 999,
                mdd=round(mdd),big=round(min(pnls)),byreason=byr)

if __name__=="__main__":
    print("loading 5yr…"); bars,yrs=load(); print(f"bars {len(bars):,}  {min(yrs)}-{max(yrs)}\n")
    trs=run(bars); s=stats(trs)
    print("=== ZONE RIDER 'Calgary' 5yr (smooth 1%, break entry, gap<=70 exit, SL200, 1pt slip) ===")
    print(f"pnl={s['pnl']}  win={s['win']}%  n={s['n']}  pf={s['pf']}  maxDD={s['mdd']}  bigLoss={s['big']}")
    print(f"exits by reason: {s['byreason']}")
    print()
    print("=== per-year ===")
    print("year |   pnl  |  n  | win% | pf   | maxDD  | exits")
    for yr in range(min(yrs),max(yrs)+1):
        sub=[b for b,y in zip(bars,yrs) if y==yr]
        st=stats(run(sub))
        print(f"{yr} | {st['pnl']:6} | {st['n']:3} | {st['win']:4} | {st['pf']:.2f} | {st['mdd']:6} | {st['byreason']}")
