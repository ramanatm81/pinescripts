#!/usr/bin/env python3
"""
Diagnose + fix the "support above resistance" (crossed-band) case in Zone Rider.

Base model = zone_rider_mfetrail_5yr.py (shipped Boulder logic: breach-hold entry,
SL -> MFE-trail -> floor exit). Two questions:

  A) HOW OFTEN is support > resistance, and how many entries/exits happen while crossed?
  B) Does gating entries+floor-exits on `support < resistance` (keep SL + MFE-trail
     as backstops) improve or hurt PnL? Report removed-trade W/L per fade-filters-hurt rule.

Configs:
  BOULDER      : shipped logic, no crossed-band guard.
  + BANDGATE   : block NEW entries while crossed; skip trailing-floor exit while crossed
                 (SL and MFE-trail still fire). Mirrors the .pine gate we intend to ship.
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
MFE_TRAIL = 80.0   # shipped Boulder value

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

def run(bars, piv, bandgate, diag=None):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    upB=0; dnB=0
    mfe=0.0; peak=None
    trades=[]  # (dir, pnl, crossedAtEntry, exitReason)
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
        bandsSane = resValid and supValid and support < resistance
        if diag is not None:
            diag['bars']+=1
            if crossed: diag['crossed_bars']+=1

        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH    if supValid else None
        supZoneTop=support+ZONE_WIDTH    if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None
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
            # 1) SL (always active)
            if tradeDir==1 and l<=entry-SL: trades.append((1,-SL,entryCrossed,"SL")); exited=True
            elif tradeDir==-1 and h>=entry+SL: trades.append((-1,-SL,entryCrossed,"SL")); exited=True
            # 2) MFE trailing (always active)
            if not exited and mfe>=MFE_TRIG:
                if tradeDir==1 and l<=peak-MFE_TRAIL: trades.append((1,(peak-MFE_TRAIL)-entry,entryCrossed,"MFE")); exited=True
                elif tradeDir==-1 and h>=peak+MFE_TRAIL: trades.append((-1,entry-(peak+MFE_TRAIL),entryCrossed,"MFE")); exited=True
            # 3) trailing-floor — GATED off while crossed when bandgate on
            floorOK = (not bandgate) or bandsSane
            if not exited and floorOK:
                if tradeDir==1 and supValid and l<=supZoneTop: trades.append((1,supZoneTop-entry,entryCrossed,"FLR")); exited=True
                elif tradeDir==-1 and resValid and h>=resZoneBot: trades.append((-1,entry-resZoneBot,entryCrossed,"FLR")); exited=True
            if exited:
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None

        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            # entries — gated off while crossed when bandgate on
            entryOK = (not bandgate) or bandsSane
            if entryOK:
                if upB==BREACH_BARS:
                    inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c; entryCrossed=crossed
                    if diag is not None and crossed: diag['crossed_entries']+=1
                elif dnB==BREACH_BARS:
                    inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c; entryCrossed=crossed
                    if diag is not None and crossed: diag['crossed_entries']+=1
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

    # --- Diagnostics on full sample (baseline behavior) ---
    diag=dict(bars=0,crossed_bars=0,crossed_entries=0)
    base_trs=run(bars,piv,bandgate=False,diag=diag)
    crossed_entry_trs=[t for t in base_trs if t[2]]
    print("=== A) crossed-band occurrence (BOULDER, no guard) ===")
    print(f"  bars with support>=resistance : {diag['crossed_bars']:,} / {diag['bars']:,} "
          f"({100*diag['crossed_bars']/diag['bars']:.1f}%)")
    print(f"  entries opened while crossed  : {len(crossed_entry_trs)} of {len(base_trs)} trades")
    if crossed_entry_trs:
        cw=sum(1 for t in crossed_entry_trs if t[1]-SLIP>0)
        cpnl=round(sum(t[1]-SLIP for t in crossed_entry_trs))
        print(f"    those trades W/L: {cw}W/{len(crossed_entry_trs)-cw}L  net pnl {cpnl}")
        from collections import Counter
        print(f"    exit reasons: {dict(Counter(t[3] for t in crossed_entry_trs))}")
    print()

    # --- B) full vs gated comparison ---
    print("=== B) BOULDER vs + BANDGATE (block entries + skip floor while crossed) ===")
    print(f"{'config':32} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yrs | per-year")
    for name,bg in [("BOULDER (no guard)",False),("+ BANDGATE",True)]:
        s=stat(run(bars,piv,bandgate=bg))
        ys=[stat(run(yr_bars[yr],yr_piv[yr],bandgate=bg))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name:32} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {[round(y) for y in ys]}")

    # --- removed-trade W/L: trades in BOULDER not taken under BANDGATE ---
    print("\n=== removed trades (in BOULDER, gated out by BANDGATE) ===")
    b=run(bars,piv,bandgate=False); g=run(bars,piv,bandgate=True)
    # crude set-diff by (dir,pnl) multiset is unreliable; instead re-run gated and count delta
    sb=stat(b); sg=stat(g)
    print(f"  BOULDER   n={sb['n']} pnl={sb['pnl']}")
    print(f"  BANDGATE  n={sg['n']} pnl={sg['pnl']}")
    print(f"  delta     n={sg['n']-sb['n']:+d} pnl={sg['pnl']-sb['pnl']:+d}")
