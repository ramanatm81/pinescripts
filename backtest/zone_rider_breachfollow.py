#!/usr/bin/env python3
"""
Zone Rider variant: breach-confirm entry + trailing-floor touch exit.

ENTRY (momentum, breach must HOLD):
  - Price breaks a band: high > resistance+width (upper) OR low < support-width (lower).
  - Wait breachBars (5). If at bar 5 price is STILL beyond that band, enter following
    the break: upper break -> LONG, lower break -> SHORT.
  (Consecutive-bars-breached counter: resets when price comes back inside the band;
   entry fires when the counter == breachBars, i.e. breach held for N straight bars.)

EXITS (whichever first):
  1. Trailing-floor touch: LONG exits when low <= support+width (rising upper-support band);
     SHORT exits when high >= resistance-width (falling lower-resistance band).
  2. SL 200. No TP, no gap exit.

No session blocks. smooth 1.0. Tested with/without opposite-after-win filter.
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

def run(bars, piv, oppAfterWin):
    n=len(bars)
    resistance=None; support=None
    inTrade=False; tradeDir=0; entry=None; cooldown=0; blockDir=0
    upBreachBars=0; dnBreachBars=0   # consecutive bars price beyond the band
    trades=[]  # (pnl, reason)

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
        resZoneTop=resistance+ZONE_WIDTH if resValid else None   # upper resistance band (break up)
        supZoneBot=support-ZONE_WIDTH    if supValid else None   # lower support band   (break down)
        supZoneTop=support+ZONE_WIDTH    if supValid else None   # LONG exit floor (rising)
        resZoneBot=resistance-ZONE_WIDTH if resValid else None   # SHORT exit ceiling (falling)

        # consecutive-breach counters (price still beyond the band this bar)
        upB = resValid and h > resZoneTop
        dnB = supValid and l < supZoneBot
        upBreachBars = upBreachBars+1 if upB else 0
        dnBreachBars = dnBreachBars+1 if dnB else 0

        # ---- manage open trade ----
        if inTrade:
            exited=False
            if tradeDir==1 and l<=entry-SL:
                trades.append((-SL,"SL",1)); exited=True
            elif tradeDir==-1 and h>=entry+SL:
                trades.append((-SL,"SL",-1)); exited=True
            if not exited:
                # trailing-floor touch exit
                if tradeDir==1 and supValid and l<=supZoneTop:
                    trades.append((supZoneTop-entry,"TOUCH",1)); exited=True
                elif tradeDir==-1 and resValid and h>=resZoneBot:
                    trades.append((entry-resZoneBot,"TOUCH",-1)); exited=True
            if exited:
                pnl=trades[-1][0]; d=tradeDir
                inTrade=False; tradeDir=0; entry=None; cooldown=COOLDOWN
                if oppAfterWin: blockDir = d if pnl>0 else 0

        if cooldown>0 and not inTrade: cooldown-=1

        # ---- entry: breach held for exactly BREACH_BARS bars, follow the break ----
        if (not inTrade) and cooldown==0:
            longDue  = upBreachBars == BREACH_BARS and (blockDir != 1)
            shortDue = dnBreachBars == BREACH_BARS and (blockDir != -1)
            if longDue:
                inTrade=True; tradeDir=1; entry=c; blockDir=0
            elif shortDue:
                inTrade=True; tradeDir=-1; entry=c; blockDir=0
    return trades

def stats(trs, side=None):
    if side is not None:
        trs=[t for t in trs if len(t)>2 and t[2]==side]
    pnls=[t[0]-SLIP for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,win=0,pf=0,mdd=0,big=0,byr={},avg=0)
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    r=0.0;peak=0.0;mdd=0.0
    for x in pnls: r+=x;peak=max(peak,r);mdd=max(mdd,peak-r)
    byr={}
    for t in trs: byr[t[1]]=byr.get(t[1],0)+1
    return dict(n=n,pnl=round(pnl),win=round(w/n*100,1),pf=round(gp/gl,2) if gl>0 else 999,
                mdd=round(mdd),big=round(min(pnls)),byr=byr,avg=round(pnl/n,2))

if __name__=="__main__":
    print("loading + pivots…"); bars,yrs=load(); piv=precompute_pivots(bars)
    years=list(range(min(yrs),max(yrs)+1))
    idx={yr:[i for i,y in enumerate(yrs) if y==yr] for yr in years}
    yr_bars={yr:[bars[i] for i in idx[yr]] for yr in years}
    yr_piv ={yr:precompute_pivots(yr_bars[yr]) for yr in years}
    print(f"bars {len(bars):,}")
    print("config: smooth1.0 breach5-follow entry, trailing-floor touch exit, SL200, no TP/gap, no sessions\n")
    # Rule 1 = no opp-win filter.
    trs=run(bars,piv,False)
    s=stats(trs); L=stats(trs,side=1); S=stats(trs,side=-1)
    print("RULE 1 — breach-follow entry + trailing-floor exit + SL200, no filter\n")
    print(f"{'':6} | {'pnl':>7} | {'n':>5} | {'win%':>5} | {'pf':>5} | {'avg':>6} | {'maxDD':>5} | bigLoss")
    print(f"{'ALL':6} | {s['pnl']:>7} | {s['n']:>5} | {s['win']:>5} | {s['pf']:>5} | {s['avg']:>6} | {s['mdd']:>5} | {s['big']}")
    print(f"{'LONG':6} | {L['pnl']:>7} | {L['n']:>5} | {L['win']:>5} | {L['pf']:>5} | {L['avg']:>6} | {L['mdd']:>5} | {L['big']}")
    print(f"{'SHORT':6} | {S['pnl']:>7} | {S['n']:>5} | {S['win']:>5} | {S['pf']:>5} | {S['avg']:>6} | {S['mdd']:>5} | {S['big']}")
    print()
    print("=== per-year LONG vs SHORT (pnl / n) ===")
    print("year |   LONG pnl (n)   |   SHORT pnl (n)")
    for yr in years:
        t=run(yr_bars[yr],yr_piv[yr],False)
        Ly=stats(t,side=1); Sy=stats(t,side=-1)
        print(f"{yr} |  {Ly['pnl']:6} ({Ly['n']:4})   |  {Sy['pnl']:6} ({Sy['n']:4})")
