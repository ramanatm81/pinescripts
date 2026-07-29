#!/usr/bin/env python3
"""Diagnose why slope_strategy_v2 (Support Ride) takes zero trades.
Replicates the v2 entry gate and counts each sub-condition independently."""
import os, csv
from datetime import datetime, timezone, timedelta

DATA = os.environ.get("BACKTEST_DATA", "/Users/maheshk81/Downloads/data.csv")

def load():
    bars = []
    with open(DATA) as f:
        for row in csv.DictReader(f):
            t = row["time"]
            if not t: continue
            try:
                o=float(row["open"]); h=float(row["high"]); l=float(row["low"]); c=float(row["close"])
            except (ValueError, TypeError):
                continue
            dt = datetime.fromisoformat(t)
            ct = dt.astimezone(timezone(timedelta(hours=-5)))
            bars.append((ct, o, h, l, c, ct.hour*60+ct.minute))
    return bars

def run(srHalfWidth=10, rideThreshold=5.0, srZoneWidth=25.0):
    bars = load()
    highs=[b[2] for b in bars]; lows=[b[3] for b in bars]
    n=len(bars)
    lastFH=None; lastFL=None; lastFHbar=None; lastFLbar=None

    cnt = dict(bars=0, have_low=0, have_high=0, have_both=0, room=0,
               low_ge_supp=0, low_le_supp_plus=0, riding=0, riding_and_room=0,
               entries=0)
    # distribution of (low - supp) when we have a valid low, to see the geometry
    gap_hist = []  # low - supp
    w=srHalfWidth
    for bi in range(n):
        ct,o,h,l,c,ctm = bars[bi]
        cnt['bars']+=1
        # confirm pivots exactly like backtest.py
        if bi >= 2*w:
            center = bi-w
            ch=highs[center]
            left=highs[bi-2*w:center]; right=highs[center+1:bi+1]
            if all(ch>x for x in left) and all(ch>x for x in right):
                lastFH=ch; lastFHbar=center
            cl=lows[center]
            left=lows[bi-2*w:center]; right=lows[center+1:bi+1]
            if all(cl<x for x in left) and all(cl<x for x in right):
                lastFL=cl; lastFLbar=center

        supp = lastFL
        res  = lastFH
        have_low = supp is not None
        have_high= res is not None
        if have_low: cnt['have_low']+=1
        if have_high: cnt['have_high']+=1
        if have_low and have_high:
            cnt['have_both']+=1
            room = supp < res
            if room: cnt['room']+=1
        if have_low:
            gap = l - supp
            gap_hist.append(gap)
            if l >= supp: cnt['low_ge_supp']+=1
            if l <= supp + rideThreshold: cnt['low_le_supp_plus']+=1
            riding = (l >= supp) and (l <= supp + rideThreshold)
            if riding: cnt['riding']+=1
            if riding and have_high and supp < res:
                cnt['riding_and_room']+=1
    print(f"DATA={DATA}")
    print(f"params: srHalfWidth={srHalfWidth} rideThreshold={rideThreshold} srZoneWidth={srZoneWidth}")
    for k,v in cnt.items():
        pct = 100.0*v/cnt['bars'] if cnt['bars'] else 0
        print(f"  {k:20s} {v:8d}  ({pct:5.2f}%)")
    # geometry of low-vs-support gap
    if gap_hist:
        import statistics
        gh=sorted(gap_hist)
        def pct(p): return gh[int(p/100*(len(gh)-1))]
        print("\n(low - support) distribution over bars with a valid pivot low:")
        print(f"  min={gh[0]:.1f}  p10={pct(10):.1f}  p50={pct(50):.1f}  p90={pct(90):.1f}  max={gh[-1]:.1f}")
        below = sum(1 for g in gap_hist if g < 0)
        in_band = sum(1 for g in gap_hist if 0 <= g <= rideThreshold)
        print(f"  low BELOW support (gap<0): {below} ({100.0*below/len(gap_hist):.1f}%)")
        print(f"  low in [supp, supp+{rideThreshold}]: {in_band} ({100.0*in_band/len(gap_hist):.1f}%)")

if __name__=="__main__":
    run()

def run_with_sessions(srHalfWidth=10, rideThreshold=5.0):
    bars=load(); highs=[b[2] for b in bars]; lows=[b[3] for b in bars]; n=len(bars)
    lastFL=None; lastFH=None; w=srHalfWidth
    riding=0; after_sess=0
    blocked_by={}
    for bi in range(n):
        ct,o,h,l,c,ctm=bars[bi]
        if bi>=2*w:
            center=bi-w
            ch=highs[center]; left=highs[bi-2*w:center]; right=highs[center+1:bi+1]
            if all(ch>x for x in left) and all(ch>x for x in right): lastFH=ch
            cl=lows[center]; left=lows[bi-2*w:center]; right=lows[center+1:bi+1]
            if all(cl<x for x in left) and all(cl<x for x in right): lastFL=cl
        supp=lastFL; res=lastFH
        if supp is None or res is None: continue
        if not (supp<res): continue
        if not (l>=supp and l<=supp+rideThreshold): continue
        riding+=1
        # session gates (CT minutes), defaults: LNopen,preNY,lunch ON; NYopen,asia OFF
        inRTH = 510<=ctm<900; eodClose=900<=ctm<960
        lnOpen = 120<=ctm<150            # blockLNOpen=true
        preNY  = 450<=ctm<540            # blockPreNY=true
        ethOpen= 1020<=ctm<1050          # hardcoded
        lunch  = 600<=ctm<780            # blockLunch=true
        reasons=[]
        if eodClose: reasons.append('eod')
        if lnOpen: reasons.append('lnOpen')
        if preNY: reasons.append('preNY')
        if ethOpen: reasons.append('ethOpen')
        if lunch: reasons.append('lunch')
        if reasons:
            for r in reasons: blocked_by[r]=blocked_by.get(r,0)+1
        else:
            after_sess+=1
    print(f"\n=== with default session filters ===")
    print(f"  riding candidates:      {riding}")
    print(f"  survive session gates:  {after_sess}")
    print(f"  blocked-by breakdown:   {blocked_by}")

if __name__!='__main__':
    pass
