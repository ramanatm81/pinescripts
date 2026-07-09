#!/usr/bin/env python3
"""
Entry-fix diagnostics for Zone Rider on 5yr MNQ.

Baseline (zone_rider_5yr.py) showed the FADE entry is net-negative every year
(PF<1). This harness tests whether the entry can be fixed, holding the OFF exit
(opposite zone edge) fixed since it was the better of the two.

Hypotheses tested:
  H1 FADE (baseline)      : short on swingUp, long on swingDown  (current .pine)
  H2 MOMENTUM (flip)      : long on swingUp,  short on swingDown  (trade WITH the swing)
  H3 FADE + proximity     : fade, but only if price is within `near` pts of the level
                            (i.e. actually AT resistance/support, not 50pt away post-lag)
  H4 MOMENTUM + proximity : momentum, only if price near the level being broken
Sweeps: minSwingPts, pivotLen, slPts.

Reuses the exit engine shape from zone_rider_5yr.py. PnL in POINTS, 1pt slip.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from strategies import stats

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP=1.0
ZONE_WIDTH=25.0; MAX_PIVOT_AGE=0; COOLDOWN=20; EXIT_ON_WICK=True; USE_HARD_SL=True

def load_5yr():
    O=[];H=[];L=[];C=[];TM=[];YR=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            O.append(o);H.append(h);L.append(l);C.append(c)
            TM.append(dt.hour*60+dt.minute); YR.append(dt.year)
    return dict(O=O,H=H,L=L,C=C,TM=TM,YR=YR,n=len(C))

def pivots(H,L,plen):
    n=len(H); phv=[None]*n; plv=[None]*n
    for i in range(plen, n-plen):
        hv=H[i]; lv=L[i]; is_ph=True; is_pl=True
        for j in range(i-plen, i+plen+1):
            if j==i: continue
            if H[j]>=hv: is_ph=False
            if L[j]<=lv: is_pl=False
            if not is_ph and not is_pl: break
        conf=i+plen
        if is_ph: phv[conf]=hv
        if is_pl: plv[conf]=lv
    return phv,plv

def run(d, mode, min_swing, plen, sl_pts, near=None):
    """mode: 'fade' | 'mom'. near=None disables proximity gate; else max pts from level."""
    n=d["n"]; H=d["H"];L=d["L"];C=d["C"];TM=d["TM"]
    phv,plv=pivots(H,L,plen)
    resistance=support=resBar=supBar=None
    inTrade=False; tradeDir=0; entry=0.0; cooldown=0
    trades=[]
    for i in range(n):
        m=TM[i]
        eod=(900<=m<960)
        inBlock=(120<=m<150) or (450<=m<540) or (1020<=m<1050)   # LN, preNY, ETH (NYopen off)
        if inTrade:
            if eod or inBlock:
                px=C[i]; trades.append((px-entry) if tradeDir==1 else (entry-px))
                inTrade=False; tradeDir=0; cooldown=0
            else:
                exited=False
                if USE_HARD_SL:
                    if tradeDir==1 and L[i]<=entry-sl_pts:
                        trades.append(-sl_pts); inTrade=False; tradeDir=0; cooldown=COOLDOWN; exited=True
                    elif tradeDir==-1 and H[i]>=entry+sl_pts:
                        trades.append(-sl_pts); inTrade=False; tradeDir=0; cooldown=COOLDOWN; exited=True
                if not exited:
                    resValid = resistance is not None
                    supValid = support is not None
                    # exit at opposite ZONE EDGE (OFF mode). For a long -> res+width, short -> sup-width.
                    if tradeDir==1 and resValid:
                        lvl=resistance+ZONE_WIDTH
                        if (H[i]>=lvl):
                            trades.append(lvl-entry); inTrade=False; tradeDir=0; cooldown=COOLDOWN
                    elif tradeDir==-1 and supValid:
                        lvl=support-ZONE_WIDTH
                        if (L[i]<=lvl):
                            trades.append(entry-lvl); inTrade=False; tradeDir=0; cooldown=COOLDOWN
        swingUp=swingDown=False
        if phv[i] is not None:
            prev=resistance; resistance=phv[i]; resBar=i-plen
            if prev is not None and (phv[i]-prev)>=min_swing: swingUp=True
        if plv[i] is not None:
            prev=support; support=plv[i]; supBar=i-plen
            if prev is not None and (prev-plv[i])>=min_swing: swingDown=True
        if cooldown>0 and not inTrade: cooldown-=1
        canEnter=(not inTrade) and (not eod) and (not inBlock) and cooldown==0
        if canEnter:
            # proximity gate: how far is current close from the just-confirmed level?
            up_ok = dn_ok = True
            if near is not None:
                if swingUp   and resistance is not None: up_ok = abs(C[i]-resistance)<=near
                if swingDown and support    is not None: dn_ok = abs(C[i]-support)<=near
            if mode=='fade':
                # short the up-swing (into resistance), long the down-swing (into support)
                if swingUp and up_ok:      inTrade=True; tradeDir=-1; entry=C[i]
                elif swingDown and dn_ok:  inTrade=True; tradeDir=1;  entry=C[i]
            else:  # momentum: go WITH the swing
                if swingUp and up_ok:      inTrade=True; tradeDir=1;  entry=C[i]
                elif swingDown and dn_ok:  inTrade=True; tradeDir=-1; entry=C[i]
    return trades

def adj(tr): return [t-SLIP for t in tr]

def line(tag, tr):
    st=stats(adj(tr))
    print(f"{tag:<34} pnl={st['pnl']:9.0f} win{st['winrate']:4.0f}% n{st['n']:5d} pf{st['pf']:.2f} avg{st['avg']:+.2f}")
    return st

if __name__=="__main__":
    print("loading 5yr…"); d=load_5yr(); print(f"bars {d['n']:,}\n")

    print("=== H1/H2: direction (minSwing=50, pivotLen=10, SL=200, no proximity) ===")
    line("H1 FADE (baseline .pine)",     run(d,'fade',50,10,200))
    line("H2 MOMENTUM (flip direction)", run(d,'mom', 50,10,200))

    print("\n=== H3/H4: + proximity gate (price within `near` pts of level) ===")
    for near in (15,30,50):
        line(f"H3 FADE near<={near}",     run(d,'fade',50,10,200,near=near))
    for near in (15,30,50):
        line(f"H4 MOM  near<={near}",     run(d,'mom', 50,10,200,near=near))

    print("\n=== minSwing sweep (best direction so far, no proximity) ===")
    for ms in (30,50,80,120):
        line(f"FADE minSwing={ms}", run(d,'fade',ms,10,200))
        line(f"MOM  minSwing={ms}", run(d,'mom', ms,10,200))

    print("\n=== SL sweep (fade & mom, minSwing=50) ===")
    for sl in (50,100,200,300):
        line(f"FADE SL={sl}", run(d,'fade',50,10,sl))
        line(f"MOM  SL={sl}", run(d,'mom', 50,10,sl))

    print("\n=== pivotLen sweep (tighter/looser swings) ===")
    for pl in (5,10,20):
        line(f"FADE pivotLen={pl}", run(d,'fade',50,pl,200))
        line(f"MOM  pivotLen={pl}", run(d,'mom', 50,pl,200))
