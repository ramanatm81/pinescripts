#!/usr/bin/env python3
"""
SPREAD GATE: skip ALL entries when |support - resistance| > maxSpread pts (configurable).
Only take trades when the smoothed band is tight. Everything else = current Boulder logic.

Rationale: wide spread == the stale/crossed regime where the geometry misbehaves
(Jul 10 spread was 255pts). Tight band == price actually near a real level.

Honest fills: crossed FLR flushes still booked at next-bar open (as in realfill). But with
a tight-spread gate, crossed entries are mostly excluded anyway.

Sweep maxSpread to see the tradeoff.
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
            try: o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((o,h,l,c)); yrs.append(dt.year)
    return bars,yrs

def precompute_pivots(bars):
    n=len(bars); highs=[b[1] for b in bars]; lows=[b[2] for b in bars]; w=PIVOT_LEN
    piv=[(None,None)]*n
    for bi in range(2*w,n):
        center=bi-w; ch=highs[center]; cl=lows[center]
        ph=ch if (all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1])) else None
        pl=cl if (all(cl<x for x in lows[bi-2*w:center])  and all(cl<x for x in lows[center+1:bi+1]))  else None
        piv[bi]=(ph,pl)
    return piv

def run(bars,piv,maxSpread):
    # maxSpread: 0 = gate OFF (no limit); else block entries when |sup-res| > maxSpread
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0; upB=0; dnB=0
    mfe=0.0; peak=None; entryBar=None; entryCrossed=False
    trades=[]
    for bi in range(n):
        o,h,l,c=bars[bi]; phVal,plVal=piv[bi]
        if phVal is not None:
            thr=SMOOTH/100.0*c
            if resistance is None or abs(phVal-resistance)>=thr: resistance=phVal
        if plVal is not None:
            thr=SMOOTH/100.0*c
            if support is None or abs(plVal-support)>=thr: support=plVal
        resValid=resistance is not None; supValid=support is not None
        crossed=resValid and supValid and support>=resistance
        spread = abs(support-resistance) if (resValid and supValid) else None
        spreadOK = (maxSpread<=0) or (spread is not None and spread<=maxSpread)

        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH if supValid else None
        supZoneTop=support+ZONE_WIDTH if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None
        upB=upB+1 if (resValid and h>resZoneTop) else 0
        dnB=dnB+1 if (supValid and l<supZoneBot) else 0

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
                # honest booking: crossed FLR flush -> next-bar open fill
                if reason=="FLR" and entryCrossed:
                    fill=o; pnl=(fill-entry) if tradeDir==1 else (entry-fill)
                trades.append(dict(dir=tradeDir,pnl=pnl-SLIP,reason=reason,crossed=entryCrossed))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None

        if cooldown>0 and not inTrade: cooldown-=1
        # ENTRY — gated by spread. Exits above are NOT gated (always manage open trades).
        if (not inTrade) and cooldown==0 and spreadOK:
            if upB==BREACH_BARS:
                inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c; entryBar=bi; entryCrossed=crossed
            elif dnB==BREACH_BARS:
                inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c; entryBar=bi; entryCrossed=crossed
    return trades

def stat(trs):
    p=[t['pnl'] for t in trs]; n=len(p)
    if n==0: return dict(n=0,pnl=0,pf=0.0,win=0,mdd=0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    r=0.0;pk=0.0;mdd=0.0
    for x in p: r+=x;pk=max(pk,r);mdd=max(mdd,pk-r)
    return dict(n=n,pnl=round(sum(p)),pf=round(gp/gl,2) if gl>0 else 999,win=round(w/n*100,1),mdd=round(mdd))

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}   (all fills honest; crossed FLR booked at next-bar open)\n")
    print(f"{'maxSpread':>10} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yrs | per-year")
    for ms in [0, 200, 150, 100, 75, 50, 40, 30, 25]:
        s=stat(run(bars,piv,ms))
        ys=[stat(run(yr_bars[yr],yr_piv[yr],ms))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        lab = "OFF" if ms==0 else str(ms)
        star = "  <- your default (100)" if ms==100 else ""
        print(f"{lab:>10} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {[round(y) for y in ys]}{star}")
