#!/usr/bin/env python3
"""
Zone Rider — VWAP-band FADE (new logic per user 2026-07-10):
  Levels = daily-anchored VWAP +/- 2sigma (volume-weighted stdev), reset each session day.
  ENTRY (mean-reversion fade, proximity +/-10):
    SHORT when high >= vwapUpper - 10   (price near/through the upper 2sigma = resistance)
    LONG  when low  <= vwapLower + 10   (price near/through the lower 2sigma = support)
  EXIT (first hit): SL 100 -> MFE trail(100/80) -> fade-to-mean at VWAP.
    long exits when high >= vwapMean ; short exits when low <= vwapMean.
  Cooldown 20 bars after exit. One position at a time. 1pt slippage/trade.

VWAP anchor: new calendar day in the CSV's session tz (America/Chicago, matching repo).
Result reported PER YEAR (pnl, n, pf, win, mdd).
"""
import csv
from datetime import datetime, timezone, timedelta

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0
COOLDOWN=20
SL=100.0
MFE_TRIG=100.0
MFE_TRAIL=80.0
NEAR=10.0
KSIGMA=2.0

def load():
    bars=[]  # (h,l,c,vol,daykey,year)
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
                v=float(row.get("Volume") or row.get("volume") or 0.0)
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-6)))  # CT-ish
            bars.append((h,l,c,v,dt.date(),dt.year))
    return bars

def vwap_bands(bars):
    """daily-anchored cumulative VWAP + volume-weighted 2sigma bands. Returns list of (mean,up,lo)."""
    out=[]
    curday=None; cumV=0.0; cumPV=0.0; cumPPV=0.0
    for (h,l,c,v,dk,yr) in bars:
        tp=(h+l+c)/3.0
        if dk!=curday:
            curday=dk; cumV=0.0; cumPV=0.0; cumPPV=0.0
        vv = v if v>0 else 1.0   # guard zero-volume bars so VWAP still advances
        cumV+=vv; cumPV+=tp*vv; cumPPV+=tp*tp*vv
        mean=cumPV/cumV
        var=max(cumPPV/cumV - mean*mean, 0.0)
        sd=var**0.5
        out.append((mean, mean+KSIGMA*sd, mean-KSIGMA*sd))
    return out

def run(bars, bands):
    n=len(bars)
    inTrade=False; tradeDir=0; entry=None; cooldown=0
    mfe=0.0; peak=None
    trades=[]  # (dir,pnl,year,reason)
    for bi in range(n):
        h,l,c,v,dk,yr = bars[bi]
        mean,up,lo = bands[bi]
        if inTrade:
            if tradeDir==1:
                if h-entry>mfe: mfe=h-entry
                peak=max(peak,h)
            else:
                if entry-l>mfe: mfe=entry-l
                peak=min(peak,l)
            reason=None; pnl=None
            # 1) SL 100
            if tradeDir==1 and l<=entry-SL: pnl=-SL; reason="SL"
            elif tradeDir==-1 and h>=entry+SL: pnl=-SL; reason="SL"
            # 2) MFE trail
            if reason is None and mfe>=MFE_TRIG:
                if tradeDir==1 and l<=peak-MFE_TRAIL: pnl=(peak-MFE_TRAIL)-entry; reason="MFE"
                elif tradeDir==-1 and h>=peak+MFE_TRAIL: pnl=entry-(peak+MFE_TRAIL); reason="MFE"
            # 3) fade-to-mean at VWAP
            if reason is None:
                if tradeDir==1 and h>=mean: pnl=mean-entry; reason="MEAN"
                elif tradeDir==-1 and l<=mean: pnl=entry-mean; reason="MEAN"
            if reason is not None:
                trades.append((tradeDir, pnl-SLIP, yr, reason))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None

        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
            # fade entries with +/-10 proximity to the band
            shortTrig = h >= up - NEAR
            longTrig  = l <= lo + NEAR
            # if both (shouldn't in practice), prefer the side price is closer to
            if shortTrig and not longTrig:
                inTrade=True; tradeDir=-1; entry=c; mfe=0.0; peak=c
            elif longTrig and not shortTrig:
                inTrade=True; tradeDir=1;  entry=c; mfe=0.0; peak=c
            elif shortTrig and longTrig:
                # degenerate: take the nearer band
                if (up-c) <= (c-lo):
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
    print(f"bars {len(bars):,}\n")
    trs=run(bars,bands)
    s=stat(trs)
    years=sorted(set(b[5] for b in bars))
    print("Zone Rider — VWAP ±2σ FADE | SHORT@up−10 / LONG@lo+10 | SL100 · MFE100/80 · exit→VWAP mean\n")
    print(f"{'year':>6} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>6} {'mdd':>6}")
    pos=0
    for yr in years:
        sy=stat([t for t in trs if t[2]==yr])
        if sy['pnl']>0: pos+=1
        print(f"{yr:>6} | {sy['pnl']:>7} {sy['n']:>5} {sy['pf']:>5} {sy['win']:>6} {sy['mdd']:>6}")
    print(f"{'-'*44}")
    print(f"{'TOTAL':>6} | {s['pnl']:>7} {s['n']:>5} {s['pf']:>5} {s['win']:>6} {s['mdd']:>6}   ({pos}/{len(years)} yrs +)")
    # exit-reason mix
    from collections import Counter
    print("\nexit reasons:", dict(Counter(t[3] for t in trs)))
    print("dir mix: long", sum(1 for t in trs if t[0]==1), " short", sum(1 for t in trs if t[0]==-1))
