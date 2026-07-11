#!/usr/bin/env python3
"""
AUDIT: is 'support>=resistance' rare (only-now) or common over 5yr? And are the crossed
trades' profits the FLR-artifact (booked at supZoneTop-entry, a guaranteed-positive fake)?

For each crossed-entry trade under BOULDER, record:
  - entry price, exit reason, booked pnl
  - bars_held (how many bars from entry to exit)  -> 1-bar flushes = the churn artifact
  - for FLR longs: is supZoneTop ABOVE entry at entry-bar? (=> instant guaranteed 'win')
"""
import csv
from datetime import datetime, timezone, timedelta

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0; PIVOT_LEN=10; ZONE_WIDTH=25.0; COOLDOWN=20; SMOOTH=1.0
SL=200.0; BREACH_BARS=5; MFE_TRIG=100.0; MFE_TRAIL=80.0

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

def run(bars,piv,yrs):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0; upB=0; dnB=0
    mfe=0.0; peak=None; entryBar=None; entryCrossed=False; entrySupZoneTop=None; entryResZoneBot=None
    trades=[]  # dict per trade
    crossed_bars=0; total_bars=0
    crossed_year=dict()
    for bi in range(n):
        h,l,c=bars[bi]; phVal,plVal=piv[bi]
        if phVal is not None:
            thr=SMOOTH/100.0*c
            if resistance is None or abs(phVal-resistance)>=thr: resistance=phVal
        if plVal is not None:
            thr=SMOOTH/100.0*c
            if support is None or abs(plVal-support)>=thr: support=plVal
        resValid=resistance is not None; supValid=support is not None
        crossed=resValid and supValid and support>=resistance
        if resValid and supValid:
            total_bars+=1
            if crossed:
                crossed_bars+=1
                crossed_year[yrs[bi]]=crossed_year.get(yrs[bi],0)+1
        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH if supValid else None
        supZoneTop=support+ZONE_WIDTH if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None
        upB=upB+1 if (resValid and h>resZoneTop) else 0
        dnB=dnB+1 if (supValid and l<supZoneBot) else 0

        exited=False
        if inTrade:
            if tradeDir==1:
                if h-entry>mfe: mfe=h-entry
                peak=max(peak,h)
            else:
                if entry-l>mfe: mfe=entry-l
                peak=min(peak,l)
            reason=None; pnl=None
            if tradeDir==1 and l<=entry-SL: pnl=-SL; reason="SL"
            elif tradeDir==-1 and h>=entry+SL: pnl=-SL; reason="SL"
            if reason is None and mfe>=MFE_TRIG:
                if tradeDir==1 and l<=peak-MFE_TRAIL: pnl=(peak-MFE_TRAIL)-entry; reason="MFE"
                elif tradeDir==-1 and h>=peak+MFE_TRAIL: pnl=entry-(peak+MFE_TRAIL); reason="MFE"
            if reason is None:
                if tradeDir==1 and supValid and l<=supZoneTop: pnl=supZoneTop-entry; reason="FLR"
                elif tradeDir==-1 and resValid and h>=resZoneBot: pnl=entry-resZoneBot; reason="FLR"
            if reason is not None:
                trades.append(dict(dir=tradeDir,pnl=pnl-SLIP,reason=reason,crossed=entryCrossed,
                                   bars_held=bi-entryBar,
                                   floorAboveEntry=(entrySupZoneTop is not None and tradeDir==1 and entrySupZoneTop>entry) or
                                                   (entryResZoneBot is not None and tradeDir==-1 and entryResZoneBot<entry)))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None; exited=True

        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            if upB==BREACH_BARS:
                inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c; entryBar=bi; entryCrossed=crossed
                entrySupZoneTop=supZoneTop; entryResZoneBot=resZoneBot
            elif dnB==BREACH_BARS:
                inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c; entryBar=bi; entryCrossed=crossed
                entrySupZoneTop=supZoneTop; entryResZoneBot=resZoneBot
    return trades,crossed_bars,total_bars,crossed_year

if __name__=="__main__":
    print("loading…"); bars,yrs=load(); piv=precompute_pivots(bars)
    trades,cb,tb,cy=run(bars,piv,yrs)
    print(f"\ncrossed bars: {cb:,}/{tb:,} = {100*cb/tb:.1f}% of valid-band bars")
    print("crossed bars per year:", {y:cy.get(y,0) for y in sorted(set(yrs))})
    ct=[t for t in trades if t['crossed']]
    print(f"\ncrossed-entry trades: {len(ct)} of {len(trades)}")
    # how many are 1-bar flushes?
    flush=[t for t in ct if t['bars_held']<=1]
    flr=[t for t in ct if t['reason']=='FLR']
    floorfake=[t for t in ct if t['reason']=='FLR' and t['floorAboveEntry']]
    print(f"  reason=FLR         : {len(flr)}  (pnl {round(sum(x['pnl'] for x in flr))})")
    print(f"  1-bar flushes      : {len(flush)}  (pnl {round(sum(x['pnl'] for x in flush))})")
    print(f"  FLR w/ floor booked FAVORABLE at entry (inverted-artifact): {len(floorfake)}  (pnl {round(sum(x['pnl'] for x in floorfake))})")
    win=sum(1 for t in ct if t['pnl']>0)
    print(f"  crossed-trade win rate {round(100*win/len(ct),1)}%  total pnl {round(sum(t['pnl'] for t in ct))}")
    # distribution of bars_held for crossed FLR trades
    import statistics
    bh=[t['bars_held'] for t in flr]
    if bh:
        print(f"  crossed-FLR bars_held: min {min(bh)} median {statistics.median(bh)} mean {round(statistics.mean(bh),1)} max {max(bh)}")
