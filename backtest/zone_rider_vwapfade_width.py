#!/usr/bin/env python3
"""
Zone Rider — VWAP ±2σ FADE + BAND-WIDTH GATE (per user 2026-07-11):
  Levels = daily-anchored VWAP +/- 2sigma.
  ENTRY (fade / mean-reversion, +/-10 proximity):
    SHORT when high >= vwapUpper - 10   (near resistance)
    LONG  when low  <= vwapLower + 10   (near support)
  NEW GATE: only take a trade when band width (upper - lower) > W pts. else no trade.
            (wide band = room to mean-revert; tight band = chop, skip)
  EXIT (first hit): SL 100 -> MFE trail(100/80) -> fade-to-mean at VWAP.
  Cooldown 20. One position. 1pt slip. Sweep W in {0,50,100,150,200}. Per-year.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0; COOLDOWN=20; SL=100.0; MFE_TRIG=100.0; MFE_TRAIL=80.0; NEAR=10.0; KSIGMA=2.0

def load():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
                v=float(row.get("Volume") or row.get("volume") or 0.0)
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-6)))
            bars.append((h,l,c,v,dt.date(),dt.year))
    return bars

def vwap_bands(bars):
    out=[]; curday=None; cumV=0.0; cumPV=0.0; cumPPV=0.0
    for (h,l,c,v,dk,yr) in bars:
        tp=(h+l+c)/3.0
        if dk!=curday: curday=dk; cumV=0.0; cumPV=0.0; cumPPV=0.0
        vv=v if v>0 else 1.0
        cumV+=vv; cumPV+=tp*vv; cumPPV+=tp*tp*vv
        mean=cumPV/cumV; var=max(cumPPV/cumV-mean*mean,0.0); sd=var**0.5
        out.append((mean,mean+KSIGMA*sd,mean-KSIGMA*sd))
    return out

def run(bars, bands, minWidth):
    n=len(bars)
    inTrade=False; tradeDir=0; entry=None; cooldown=0; mfe=0.0; peak=None
    trades=[]
    for bi in range(n):
        h,l,c,v,dk,yr=bars[bi]; mean,up,lo=bands[bi]
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
            if reason is None:  # fade-to-mean
                if tradeDir==1 and h>=mean: pnl=mean-entry; reason="MEAN"
                elif tradeDir==-1 and l<=mean: pnl=entry-mean; reason="MEAN"
            if reason is not None:
                trades.append((tradeDir,pnl-SLIP,yr,reason))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None
        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            width = up - lo
            if width > minWidth:                    # BAND-WIDTH GATE
                shortTrig = h >= up - NEAR          # fade near resistance
                longTrig  = l <= lo + NEAR          # fade near support
                if shortTrig and not longTrig:
                    inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c
                elif longTrig and not shortTrig:
                    inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c
                elif shortTrig and longTrig:
                    if (up-c)<=(c-lo):
                        inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c
                    else:
                        inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c
    return trades

def stat(trs):
    p=[t[1] for t in trs]; n=len(p)
    if n==0: return dict(n=0,pnl=0,pf=0.0,win=0.0,mdd=0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    r=0.0;pk=0.0;mdd=0.0
    for x in p: r+=x;pk=max(pk,r);mdd=max(mdd,pk-r)
    return dict(n=n,pnl=round(sum(p)),pf=round(gp/gl,2) if gl>0 else 999,win=round(w/n*100,1),mdd=round(mdd))

if __name__=="__main__":
    print("loading + VWAP bands…"); bars=load(); bands=vwap_bands(bars)
    years=sorted(set(b[5] for b in bars))
    print(f"bars {len(bars):,}")
    print("Zone Rider — VWAP ±2σ FADE (short@resistance / long@support) + band-width gate\n")
    for W in [0,50,100,150,200]:
        trs=run(bars,bands,W)
        s=stat(trs); pos=0
        lab = "no gate" if W==0 else f"width>{W}"
        print(f"=== {lab} ===")
        print(f"{'year':>6} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>6} {'mdd':>6}")
        for yr in years:
            sy=stat([t for t in trs if t[2]==yr])
            if sy['pnl']>0: pos+=1
            print(f"{yr:>6} | {sy['pnl']:>7} {sy['n']:>5} {sy['pf']:>5} {sy['win']:>6} {sy['mdd']:>6}")
        star = "  <- your 100pt gate" if W==100 else ""
        print(f"{'TOTAL':>6} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>6} {s['mdd']:>6}   ({pos}/{len(years)} yrs +){star}\n")
