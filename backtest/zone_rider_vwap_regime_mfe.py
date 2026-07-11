#!/usr/bin/env python3
"""
Zone Rider — VWAP ±2σ REGIME SPLIT + SMALL MFE on the fade leg (per user 2026-07-11).
Hypothesis: the narrow-band FADE loses because its exit lets small reversions give back.
A SMALL MFE (arm ~15-40 pts, trail ~10-20) locks the little wins that fade scalping is for.

  NARROW (width < thresh): FADE. short@resistance/long@support (±10).
    Exits (first hit): SL(fadeSL) -> small MFE(trig/trail) -> opposite band (runner target).
  WIDE (width >= thresh): MOMENTUM. long break up / short break down.
    Exits: SL100 -> MFE100/80.

Sweep fade MFE (trig/trail) over {15/10, 20/12, 30/15, 40/20} at a few thresh/fadeSL.
Per-year + regime breakdown for the fade leg.
"""
import csv
from datetime import datetime, timezone, timedelta

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0; COOLDOWN=20; NEAR=10.0; KSIGMA=2.0
MOM_SL=100.0; MOM_MFE_TRIG=100.0; MOM_MFE_TRAIL=80.0

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

def run(bars, bands, thresh, fadeSL, fadeMfeTrig, fadeMfeTrail):
    n=len(bars)
    inTrade=False; tradeDir=0; entry=None; cooldown=0; mfe=0.0; peak=None; regime=None
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
            if regime=='fade':
                sl=fadeSL; mtrig=fadeMfeTrig; mtrail=fadeMfeTrail
            else:
                sl=MOM_SL; mtrig=MOM_MFE_TRIG; mtrail=MOM_MFE_TRAIL
            reason=None; pnl=None
            if tradeDir==1 and l<=entry-sl: pnl=-sl; reason="SL"
            elif tradeDir==-1 and h>=entry+sl: pnl=-sl; reason="SL"
            if reason is None and mfe>=mtrig:
                if tradeDir==1 and l<=peak-mtrail: pnl=(peak-mtrail)-entry; reason="MFE"
                elif tradeDir==-1 and h>=peak+mtrail: pnl=entry-(peak+mtrail); reason="MFE"
            if reason is None and regime=='fade':
                if tradeDir==1 and h>=up: pnl=up-entry; reason="OPPBAND"
                elif tradeDir==-1 and l<=lo: pnl=entry-lo; reason="OPPBAND"
            if reason is not None:
                trades.append((tradeDir,pnl-SLIP,yr,reason,regime))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None; regime=None
        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            width=up-lo
            shortNear = h >= up - NEAR
            longNear  = l <= lo + NEAR
            if width < thresh:   # FADE
                if shortNear and not longNear:
                    inTrade=True; tradeDir=-1; entry=c; regime='fade'; mfe=0.0; peak=c
                elif longNear and not shortNear:
                    inTrade=True; tradeDir=1; entry=c; regime='fade'; mfe=0.0; peak=c
                elif shortNear and longNear:
                    if (up-c)<=(c-lo): inTrade=True; tradeDir=-1; entry=c; regime='fade'; mfe=0.0; peak=c
                    else: inTrade=True; tradeDir=1; entry=c; regime='fade'; mfe=0.0; peak=c
            else:                # MOMENTUM
                if longNear and not shortNear:
                    inTrade=True; tradeDir=1; entry=c; regime='mom'; mfe=0.0; peak=c
                elif shortNear and not longNear:
                    inTrade=True; tradeDir=-1; entry=c; regime='mom'; mfe=0.0; peak=c
                elif longNear and shortNear:
                    if (up-c)<=(c-lo): inTrade=True; tradeDir=1; entry=c; regime='mom'; mfe=0.0; peak=c
                    else: inTrade=True; tradeDir=-1; entry=c; regime='mom'; mfe=0.0; peak=c
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
    print("REGIME SPLIT + small fade-MFE. thresh/fadeSL fixed per block; sweep fade MFE trig/trail.\n")
    mfeGrid=[(15,10),(20,12),(30,15),(40,20)]
    for (th,fsl) in [(50,50),(70,50),(50,30)]:
        print(f"########## thresh<{th} fade, fadeSL={fsl} ##########")
        print(f"{'fadeMFE':>10} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yr | per-year | fadeLeg pnl")
        for (mt,mr) in mfeGrid:
            trs=run(bars,bands,th,fsl,mt,mr)
            s=stat(trs); line=[]; pos=0
            for yr in years:
                py=stat([t for t in trs if t[2]==yr])['pnl']
                if py>0: pos+=1
                line.append(py)
            fadeleg=stat([t for t in trs if t[4]=='fade'])['pnl']
            print(f"{(str(mt)+'/'+str(mr)):>10} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {line} | {fadeleg}")
        print()
