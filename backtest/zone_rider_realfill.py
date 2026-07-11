#!/usr/bin/env python3
"""
Re-run with REALISTIC crossed-floor fill.

Problem proven by crossaudit: when entered crossed (support>=resistance), a LONG's floor
supZoneTop sits ABOVE entry, so the harness booked exit at supZoneTop-entry = guaranteed
fake +profit, and the trade is a 1-bar flush. Live that is a losing 1-min round-trip.

FIX to the harness fill model: if a FLR exit fires while the floor was already breached at
entry (i.e. the "instant flush" case), do NOT book supZoneTop-entry. Book the exit at the
realistic next-bar fill = OPEN of the bar AFTER the entry bar (earliest tradeable price on
calc_on_every_tick=false), minus slippage. That is what actually fills live.

We also need OPEN, so load it.

Configs:
  ORIG-naive  : original logic, original (fake) fill  -> reproduces +98k
  ORIG-real   : original logic, REALISTIC crossed fill -> the honest number for the original
  CROSSFIX    : correct-direction + disable inverted floor, realistic fill throughout
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

def run(bars,piv,mode):
    # mode: 'orig_naive', 'orig_real', 'crossfix'
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
        resZoneTop=resistance+ZONE_WIDTH if resValid else None
        supZoneBot=support-ZONE_WIDTH if supValid else None
        supZoneTop=support+ZONE_WIDTH if supValid else None
        resZoneBot=resistance-ZONE_WIDTH if resValid else None

        # breach counters
        if mode=='crossfix' and crossed:
            dSup=abs(c-support); dRes=abs(c-resistance)
            upB=upB+1 if (dRes<dSup and resValid and h>resZoneTop) else 0
            dnB=dnB+1 if (dSup<dRes and supValid and l<supZoneBot) else 0
        else:
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
                # trailing floor. Under crossfix, DISABLE while entered-crossed.
                floorActive = not (mode=='crossfix' and entryCrossed)
                if floorActive:
                    if tradeDir==1 and supValid and l<=supZoneTop: pnl=supZoneTop-entry; reason="FLR"
                    elif tradeDir==-1 and resValid and h>=resZoneBot: pnl=entry-resZoneBot; reason="FLR"
            if reason is not None:
                # REALISTIC FILL: for orig_real, if this is a crossed-entry FLR that's an
                # instant/near-instant flush (floor was already breached at entry so it
                # exits at/near next bar), book at the CURRENT bar open (earliest fill),
                # not the fictional supZoneTop-entry.
                if mode=='orig_real' and reason=="FLR" and entryCrossed:
                    fill = o  # this bar's open = realistic exit fill
                    pnl = (fill-entry) if tradeDir==1 else (entry-fill)
                trades.append(dict(dir=tradeDir,pnl=pnl-SLIP,reason=reason,crossed=entryCrossed,held=bi-entryBar))
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN; mfe=0.0; peak=None

        if cooldown>0 and not inTrade: cooldown-=1
        if (not inTrade) and cooldown==0:
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
    print(f"bars {len(bars):,}\n")
    print(f"{'config':26} | {'pnl':>8} {'n':>5} {'pf':>5} {'win':>5} {'mdd':>6} | +yrs | per-year")
    for name,mode in [("ORIG naive (fake fill)","orig_naive"),
                      ("ORIG realistic fill","orig_real"),
                      ("CROSSFIX (realistic)","crossfix")]:
        s=stat(run(bars,piv,mode))
        ys=[stat(run(yr_bars[yr],yr_piv[yr],mode))['pnl'] for yr in years]
        pos=sum(1 for y in ys if y>0)
        print(f"{name:26} | {s['pnl']:>8} {s['n']:>5} {s['pf']:>5} {s['win']:>5} {s['mdd']:>6} | {pos}/{len(years)} | {[round(y) for y in ys]}")

    print("\n=== crossed-entry trades: naive vs realistic booking ===")
    for name,mode in [("ORIG naive","orig_naive"),("ORIG realistic","orig_real")]:
        ct=[t for t in run(bars,piv,mode) if t['crossed']]
        s=stat(ct)
        print(f"  {name:16} n={s['n']:>4} pnl={s['pnl']:>7} pf={s['pf']:>5} win={s['win']:>5}")
