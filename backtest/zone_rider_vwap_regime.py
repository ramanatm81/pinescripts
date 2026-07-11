#!/usr/bin/env python3
"""
Zone Rider — VWAP ±2σ REGIME SPLIT by band width (per user 2026-07-11):
  Levels = daily-anchored VWAP +/- 2sigma. width = upper - lower.

  NARROW regime (width < THRESH): FADE (mean-reversion, many small trades)
    SHORT when high >= upper - 10  -> cover at OPPOSITE band (lower), live/trailing
    LONG  when low  <= lower + 10  -> cover at OPPOSITE band (upper)
    SL = fadeSL (sweep 20/30/50), backstop. MFE trail also active.

  WIDE regime (width >= THRESH): MOMENTUM (ride the break)
    LONG  when high >= upper - 10   (break up)
    SHORT when low  <= lower + 10   (break down)
    SL = 100, MFE trail 100/80.

  Regime decided at ENTRY by the band width on that bar; the trade keeps its regime's
  exit rules until closed. Cooldown 20. One position. 1pt slip.
  Sweep THRESH in {50,70,90} x fadeSL in {20,30,50}. Per-year.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0; COOLDOWN=20; NEAR=10.0; KSIGMA=2.0
MOM_SL=100.0; MFE_TRIG=100.0; MFE_TRAIL=80.0

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

def run(bars, bands, thresh, fadeSL):
    n=len(bars)
    inTrade=False; tradeDir=0; entry=None; cooldown=0; mfe=0.0; peak=None
    regime=None  # 'fade' or 'mom'
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
            sl = fadeSL if regime=='fade' else MOM_SL
            reason=None; pnl=None
            # 1) SL (regime-specific)
            if tradeDir==1 and l<=entry-sl: pnl=-sl; reason="SL"
            elif tradeDir==-1 and h>=entry+sl: pnl=-sl; reason="SL"
            # 2) MFE trail (both regimes)
            if reason is None and mfe>=MFE_TRIG:
                if tradeDir==1 and l<=peak-MFE_TRAIL: pnl=(peak-MFE_TRAIL)-entry; reason="MFE"
                elif tradeDir==-1 and h>=peak+MFE_TRAIL: pnl=entry-(peak+MFE_TRAIL); reason="MFE"
            # 3) regime target
            if reason is None:
                if regime=='fade':
                    # exit at OPPOSITE band (live/trailing): long covers at upper, short at lower
                    if tradeDir==1 and h>=up: pnl=up-entry; reason="OPPBAND"
                    elif tradeDir==-1 and l<=lo: pnl=entry-lo; reason="OPPBAND"
                # momentum: no target exit, ride via MFE/SL only
            if reason is not None:
                trades.append((tradeDir,pnl-SLIP,yr,reason,regime))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None; regime=None
        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            width=up-lo
            if width < thresh:
                # NARROW -> FADE (short near resistance, long near support)
                shortTrig = h >= up - NEAR
                longTrig  = l <= lo + NEAR
                if shortTrig and not longTrig:
                    inTrade=True; tradeDir=-1; entry=c; regime='fade'; mfe=0.0; peak=c
                elif longTrig and not shortTrig:
                    inTrade=True; tradeDir=1; entry=c; regime='fade'; mfe=0.0; peak=c
                elif shortTrig and longTrig:
                    if (up-c)<=(c-lo):
                        inTrade=True; tradeDir=-1; entry=c; regime='fade'; mfe=0.0; peak=c
                    else:
                        inTrade=True; tradeDir=1; entry=c; regime='fade'; mfe=0.0; peak=c
            else:
                # WIDE -> MOMENTUM (long break up, short break down)
                longTrig  = h >= up - NEAR
                shortTrig = l <= lo + NEAR
                if longTrig and not shortTrig:
                    inTrade=True; tradeDir=1; entry=c; regime='mom'; mfe=0.0; peak=c
                elif shortTrig and not longTrig:
                    inTrade=True; tradeDir=-1; entry=c; regime='mom'; mfe=0.0; peak=c
                elif longTrig and shortTrig:
                    if (up-c)<=(c-lo):
                        inTrade=True; tradeDir=1; entry=c; regime='mom'; mfe=0.0; peak=c
                    else:
                        inTrade=True; tradeDir=-1; entry=c; regime='mom'; mfe=0.0; peak=c
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
    print(f"bars {len(bars):,}\n")
    print("VWAP ±2σ REGIME SPLIT: width<thresh=FADE(opp-band,tightSL) / width>=thresh=MOMENTUM(SL100,MFE)\n")
    print(f"{'thresh/fadeSL':>14} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yr | per-year")
    for th in [50,70,90]:
        for fsl in [20,30,50]:
            trs=run(bars,bands,th,fsl)
            s=stat(trs); line=[]; pos=0
            for yr in years:
                py=stat([t for t in trs if t[2]==yr])['pnl']
                if py>0: pos+=1
                line.append(py)
            print(f"{('th'+str(th)+'/sl'+str(fsl)):>14} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {line}")
    # regime split diagnostic on th=70/sl=30
    print("\n--- regime breakdown (th70/sl30) ---")
    trs=run(bars,bands,70,30)
    for rg in ['fade','mom']:
        rt=[t for t in trs if t[4]==rg]; s=stat(rt)
        print(f"  {rg:5} n={s['n']:>5} pnl={s['pnl']:>7} pf={s['pf']:>5} win={s['win']:>5}")
