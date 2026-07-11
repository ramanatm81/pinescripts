#!/usr/bin/env python3
"""
Does turning smoothing OFF (or changing it) keep resistance above support?
Measure % of bars where support >= resistance (crossed) across smoothSRPct values.
Smoothing only gates WHEN a level snaps to a new pivot; it does not couple sup<->res.
Hypothesis: lower smoothing = levels update more eagerly = MORE crossing, not less.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
PIVOT_LEN=10

def load():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try: h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            bars.append((h,l,c))
    return bars

def precompute_pivots(bars):
    n=len(bars); highs=[b[0] for b in bars]; lows=[b[1] for b in bars]; w=PIVOT_LEN
    piv=[(None,None)]*n
    for bi in range(2*w,n):
        center=bi-w; ch=highs[center]; cl=lows[center]
        ph=ch if (all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1])) else None
        pl=cl if (all(cl<x for x in lows[bi-2*w:center])  and all(cl<x for x in lows[center+1:bi+1]))  else None
        piv[bi]=(ph,pl)
    return piv

def crossed_pct(bars,piv,smooth):
    resistance=None; support=None
    tot=0; cross=0
    for bi in range(len(bars)):
        h,l,c=bars[bi]; phVal,plVal=piv[bi]
        if phVal is not None:
            thr=smooth/100.0*c
            if resistance is None or abs(phVal-resistance)>=thr: resistance=phVal
        if plVal is not None:
            thr=smooth/100.0*c
            if support is None or abs(plVal-support)>=thr: support=plVal
        if resistance is not None and support is not None:
            tot+=1
            if support>=resistance: cross+=1
    return tot, cross

if __name__=="__main__":
    print("loading + pivots…"); bars=load(); piv=precompute_pivots(bars)
    print(f"bars {len(bars):,}\n")
    print(f"{'smoothSRPct':>12} | {'crossed %':>10} | note")
    for s in [0.0, 0.01, 0.25, 0.5, 1.0, 2.0, 5.0]:
        tot,cross=crossed_pct(bars,piv,s)
        note = "OFF (every pivot snaps)" if s==0.0 else ("shipped default" if s==1.0 else "")
        print(f"{s:>12} | {100*cross/tot:>9.1f}% | {note}")
