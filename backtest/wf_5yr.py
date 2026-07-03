#!/usr/bin/env python3
"""
Walk-forward validation of the VWAP-reversion strategy on 5 years of 1-min MNQ
(continuous front-month, 2021-2026). This is the payoff of the big dataset: test
whether the ~1.5x-baseline edge from the 18-day sample holds across many regimes.

Loads mnq_5yr.csv (exported from the parquet). Normalizes UTC -> Chicago for
session logic. Reuses the strategies.py indicators + exit engine.

Outputs:
  - per-YEAR PnL/win/PF (regime robustness)
  - rolling walk-forward: train N months -> test next M months, rolled forward
  - summary vs the +6848 slope baseline (which itself was only an 18-day figure)
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
from strategies import ema, sma, atr, rsi, session_vwap, backtest_signals, stats

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

def load_5yr():
    O=[];H=[];L=[];C=[];V=[];TM=[];DAY=[];YR=[];MO=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"]);v=float(row["Volume"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))  # Chicago (CDT approx)
            O.append(o);H.append(h);L.append(l);C.append(c);V.append(v)
            TM.append(dt.hour*60+dt.minute); DAY.append(dt.toordinal()); YR.append(dt.year); MO.append(dt.month)
    return dict(O=O,H=H,L=L,C=C,V=V,TM=TM,DAY=DAY,YR=YR,MO=MO,n=len(C))

def vwap_reversion_signals(d):
    """The current best config: fade >=1*ATR from session VWAP, elevated-ATR
    regime, drop net-loser overnight hours 00/01/21 CT."""
    n=d["n"]; C=d["C"]; H=d["H"]; L=d["L"]; V=d["V"]; DAY=d["DAY"]; TM=d["TM"]
    vwap=session_vwap(H,L,C,V,DAY); A=atr(H,L,C,14)
    avals=sorted(a for a in A if a); med=avals[len(avals)//2] if avals else 0
    dead={0,1,21}
    sig=[0]*n
    for i in range(n):
        if not(vwap[i] and A[i] and A[i]>=med): continue
        if (TM[i]//60) in dead: continue
        dev=C[i]-vwap[i]; band=1.0*A[i]
        if dev<=-band: sig[i]=1
        elif dev>=band: sig[i]=-1
    return sig, vwap, A, med

EXIT_KW=dict(sl_pts=35,tp_pts=0,trail_trig=20,trail_dist=5,max_bars=30,cooldown=3)
SLIP=1.0
def adj(tr): return [t-SLIP for t in tr]

def slice_idx(d, pred):
    """return a shallow sub-dict of bars where pred(i) true (keeps arrays aligned)."""
    idx=[i for i in range(d["n"]) if pred(i)]
    sub={k:([d[k][i] for i in idx] if isinstance(d[k],list) else d[k]) for k in d if k!="n"}
    sub["n"]=len(idx)
    return sub

if __name__=="__main__":
    print("loading 5yr…")
    d=load_5yr()
    print(f"bars {d['n']:,}  {min(d['YR'])}-{max(d['YR'])}")
    sig,vwap,A,med=vwap_reversion_signals(d)

    # ---- full period ----
    full=stats(adj(backtest_signals(d,sig,**EXIT_KW)))
    print(f"\nFULL 5yr (1pt slip): pnl={full['pnl']:.0f} pts  win{full['winrate']:.0f}%  n{full['n']}  pf{full['pf']:.2f}")
    print(f"  ~per year avg: {full['pnl']/5:.0f} pts  (18-day slope baseline was +6848)")

    # ---- per-year breakdown (regime robustness) ----
    print("\n=== per-year ===")
    print("year |   pnl  | win% |  n   | pf")
    for yr in range(min(d['YR']),max(d['YR'])+1):
        sub=slice_idx(d, lambda i,y=yr: d['YR'][i]==y)
        s2,_,_,_=vwap_reversion_signals(sub)  # recompute VWAP/ATR within the year slice
        st=stats(adj(backtest_signals(sub,s2,**EXIT_KW)))
        print(f"{yr} | {st['pnl']:7.0f} | {st['winrate']:4.0f} | {st['n']:4d} | {st['pf']:.2f}")

    # ---- walk-forward: train on year Y (params fixed here, so 'test' = OOS year) ----
    # Since our params are fixed (not fit per-window), walk-forward here = each year is
    # an independent OOS test of the SAME config. Consistency across years = robust edge.
    print("\n=== walk-forward (same config, each year independent OOS) ===")
    yrs=list(range(min(d['YR']),max(d['YR'])+1))
    pos=neg=0
    for yr in yrs:
        sub=slice_idx(d, lambda i,y=yr: d['YR'][i]==y)
        s2,_,_,_=vwap_reversion_signals(sub)
        st=stats(adj(backtest_signals(sub,s2,**EXIT_KW)))
        tag="OK" if st['pnl']>0 else "LOSS"
        if st['pnl']>0: pos+=1
        else: neg+=1
    print(f"profitable years: {pos}/{len(yrs)}")
