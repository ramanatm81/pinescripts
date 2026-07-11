#!/usr/bin/env python3
"""
Zone Rider — VWAP-band MOMENTUM + CHOP FILTER.
Base = zone_rider_vwapmom.py best config (LONG break above +2s, SHORT below -2s;
SL100, MFE100/80, no mean-stop) = +5314 / 3-6 / PF1.04. Losing years are choppy
(2022/23/26). Test chop filters that only allow entries in trending conditions:

  F0 BASELINE       : no filter (reproduce +5314)
  F1 BAND-EXPAND    : band width > band width N bars ago (vol building)
  F2 ADX            : Wilder ADX >= thresh (trend strength) — computed on the bar series
  F3 EXTENDED       : require a STRONG break (price beyond band by extra margin, not a tag)
  F4 SLOPE          : VWAP mean rising/falling over N bars (directional session)

Report per-year for each. Goal: lift 3-6 -> 5-6/6 without gutting PnL.
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
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
                v=float(row.get("Volume") or row.get("volume") or 0.0)
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-6)))
            bars.append((o,h,l,c,v,dt.date(),dt.year))
    return bars

def vwap_bands(bars):
    out=[]; curday=None; cumV=0.0; cumPV=0.0; cumPPV=0.0
    for (o,h,l,c,v,dk,yr) in bars:
        tp=(h+l+c)/3.0
        if dk!=curday: curday=dk; cumV=0.0; cumPV=0.0; cumPPV=0.0
        vv=v if v>0 else 1.0
        cumV+=vv; cumPV+=tp*vv; cumPPV+=tp*tp*vv
        mean=cumPV/cumV; var=max(cumPPV/cumV-mean*mean,0.0); sd=var**0.5
        out.append((mean,mean+KSIGMA*sd,mean-KSIGMA*sd,sd))
    return out

def wilder_adx(bars, n=14):
    """Standard Wilder ADX on the full bar series."""
    N=len(bars); adx=[0.0]*N
    tr_s=0.0; pdm_s=0.0; ndm_s=0.0; adx_prev=None; dx_acc=[];
    prev_adx=0.0; cnt=0
    atr=0.0; pDI=0.0; nDI=0.0
    for i in range(1,N):
        o,h,l,c,v,dk,yr=bars[i]; ph=bars[i-1][1]; pl=bars[i-1][2]; pc=bars[i-1][3]
        tr=max(h-l, abs(h-pc), abs(l-pc))
        up=h-ph; dn=pl-l
        pdm=up if (up>dn and up>0) else 0.0
        ndm=dn if (dn>up and dn>0) else 0.0
        if i<=n:
            tr_s+=tr; pdm_s+=pdm; ndm_s+=ndm
            if i==n and tr_s>0:
                pDI=100*pdm_s/tr_s; nDI=100*ndm_s/tr_s
            adx[i]=0.0
            continue
        tr_s = tr_s - tr_s/n + tr
        pdm_s= pdm_s- pdm_s/n + pdm
        ndm_s= ndm_s- ndm_s/n + ndm
        pDI = 100*pdm_s/tr_s if tr_s>0 else 0.0
        nDI = 100*ndm_s/tr_s if tr_s>0 else 0.0
        dx = 100*abs(pDI-nDI)/(pDI+nDI) if (pDI+nDI)>0 else 0.0
        if i<=2*n:
            dx_acc.append(dx)
            if i==2*n:
                prev_adx=sum(dx_acc)/len(dx_acc)
            adx[i]=prev_adx
        else:
            prev_adx=(prev_adx*(n-1)+dx)/n
            adx[i]=prev_adx
    return adx

def run(bars, bands, filt, adx=None, param=None):
    n=len(bars)
    inTrade=False; tradeDir=0; entry=None; cooldown=0; mfe=0.0; peak=None
    trades=[]
    for bi in range(n):
        o,h,l,c,v,dk,yr=bars[bi]; mean,up,lo,sd=bands[bi]
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
            if reason is not None:
                trades.append((tradeDir,pnl-SLIP,yr,reason))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None
        if cooldown>0 and not inTrade: cooldown-=1

        # chop filter gate
        allow=True
        if filt=="expand":
            wN=param
            if bi>=wN:
                allow = (bands[bi][1]-bands[bi][2]) > (bands[bi-wN][1]-bands[bi-wN][2])
            else: allow=False
        elif filt=="adx":
            allow = adx[bi] >= param
        elif filt=="extended":
            allow=True  # handled in trigger below (stronger break margin)
        elif filt=="slope":
            wN=param
            allow = bi>=wN and abs(bands[bi][0]-bands[bi-wN][0]) > 0  # any directional drift; refined below
            if bi>=wN:
                slope=bands[bi][0]-bands[bi-wN][0]
            else:
                slope=0.0; allow=False

        if (not inTrade) and cooldown==0 and allow:
            margin = param if filt=="extended" else NEAR
            if filt=="extended":
                longTrig  = h >= up + margin    # STRONG break above +2s
                shortTrig = l <= lo - margin
            else:
                longTrig  = h >= up - NEAR
                shortTrig = l <= lo + NEAR
            # slope filter: only long if mean rising, only short if mean falling
            if filt=="slope":
                if slope<=0: longTrig=False
                if slope>=0: shortTrig=False
            if longTrig and not shortTrig:
                inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c
            elif shortTrig and not longTrig:
                inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c
            elif longTrig and shortTrig:
                if (up-c)<=(c-lo):
                    inTrade=True; tradeDir=1; entry=c; mfe=0.0; peak=c
                else:
                    inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c
    return trades

def stat(trs):
    p=[t[1] for t in trs]; n=len(p)
    if n==0: return dict(n=0,pnl=0,pf=0.0,win=0.0,mdd=0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    r=0.0;pk=0.0;mdd=0.0
    for x in p: r+=x;pk=max(pk,r);mdd=max(mdd,pk-r)
    return dict(n=n,pnl=round(sum(p)),pf=round(gp/gl,2) if gl>0 else 999,win=round(w/n*100,1),mdd=round(mdd))

def report(name,trs,years):
    s=stat(trs); pos=0; line=[]
    for yr in years:
        py=stat([t for t in trs if t[2]==yr])['pnl']
        if py>0: pos+=1
        line.append(py)
    print(f"{name:32} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {line}")

if __name__=="__main__":
    print("loading + VWAP bands + ADX…"); bars=load(); bands=vwap_bands(bars); adx=wilder_adx(bars)
    years=sorted(set(b[6] for b in bars))
    print(f"bars {len(bars):,}\n")
    print(f"{'config':32} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yr | per-year")
    report("F0 baseline (no filter)", run(bars,bands,None), years)
    for w in [30,60,120]:
        report(f"F1 band-expand w={w}", run(bars,bands,"expand",param=w), years)
    for a in [15,20,25]:
        report(f"F2 ADX>={a}", run(bars,bands,"adx",adx=adx,param=a), years)
    for m in [10,25,50]:
        report(f"F3 extended +{m}pts", run(bars,bands,"extended",param=m), years)
    for w in [30,60,120]:
        report(f"F4 mean-slope w={w}", run(bars,bands,"slope",param=w), years)
