#!/usr/bin/env python3
"""Sweep a library of classic 1m strategies vs the slope baseline (+6848).
Reports full-period + IS/OOS(60/40) for the best config of each family."""
import itertools
from strategies import (load, ema, sma, atr, rsi, rolling_max, rolling_min,
                        session_vwap, supertrend, backtest_signals, stats)

d=load(); n=d["n"]; C=d["C"]; H=d["H"]; L=d["L"]; V=d["V"]; DAY=d["DAY"]; TM=d["TM"]
split=int(n*0.6)

def slice_d(a,b):
    return {k:(v[a:b] if isinstance(v,list) else v) for k,v in d.items()} | {"n":b-a}

def run_is_oos(sig, **exit_kw):
    full=stats(backtest_signals(d, sig, **exit_kw))
    # rebuild signals per-slice? signals are global; just slice trades by index isn't clean.
    # Simpler: run exit engine on slice dicts with sliced signals.
    dIS=slice_d(0,split); dOOS=slice_d(split,n)
    sIS=stats(backtest_signals(dIS, sig[0:split], **exit_kw))
    sOOS=stats(backtest_signals(dOOS, sig[split:n], **exit_kw))
    return full,sIS,sOOS

def show(name, sig, **exit_kw):
    f,i,o=run_is_oos(sig,**exit_kw)
    print(f"{name:34s} FULL {f['pnl']:8.0f} win{f['winrate']:4.0f}% n{f['n']:4d} pf{f['pf']:4.2f} | IS {i['pnl']:7.0f} | OOS {o['pnl']:7.0f} win{o['winrate']:3.0f}%")
    return f

# precompute indicators
A14=atr(H,L,C,14)
vwap=session_vwap(H,L,C,V,DAY)
r14=rsi(C,14)
best_overall=[("baseline_slope",6848)]

# ---- 1) Donchian breakout (momentum) with ATR stop ----
for lb in [20,40,60]:
    hi=rolling_max(H,lb); lo=rolling_min(L,lb)
    sig=[0]*n
    for i in range(lb+1,n):
        if hi[i-1] and C[i]>hi[i-1]: sig[i]=1
        elif lo[i-1] and C[i]<lo[i-1]: sig[i]=-1
    for slm,tpm in [(1.5,3.0),(2.0,4.0)]:
        # ATR-based stop/target in points using current ATR proxy (median-ish 20)
        f=show(f"Donchian{lb} SL{slm}xATR TP{tpm}", sig,
             sl_pts=slm*15, tp_pts=tpm*15, trail_trig=30, trail_dist=10, max_bars=60)
        best_overall.append((f"Donchian{lb}",f['pnl']))

# ---- 2) VWAP mean-reversion: fade extension from VWAP ----
for band in [15,25,40]:
    sig=[0]*n
    for i in range(n):
        if vwap[i] is None: continue
        dev=C[i]-vwap[i]
        if dev<=-band: sig[i]=1   # below vwap -> long (revert up)
        elif dev>=band: sig[i]=-1
    f=show(f"VWAP revert band{band}", sig, sl_pts=30, tp_pts=0, trail_trig=25, trail_dist=8, max_bars=30, cooldown=5)
    best_overall.append((f"VWAPrev{band}",f['pnl']))

# ---- 3) VWAP trend: trade in direction of vwap slope on pullback ----
for band in [10,20]:
    sig=[0]*n
    for i in range(2,n):
        if vwap[i] is None or vwap[i-2] is None: continue
        vslope=vwap[i]-vwap[i-2]
        if vslope>0 and C[i]<vwap[i]+band and C[i]>vwap[i]: sig[i]=1
        elif vslope<0 and C[i]>vwap[i]-band and C[i]<vwap[i]: sig[i]=-1
    f=show(f"VWAP trend band{band}", sig, sl_pts=25, tp_pts=50, trail_trig=25, trail_dist=8, max_bars=40, cooldown=3)
    best_overall.append((f"VWAPtrend{band}",f['pnl']))

# ---- 4) Bollinger mean-reversion ----
for p,mult in [(20,2.0),(20,2.5)]:
    m=sma(C,p)
    sd=[None]*n
    for i in range(p-1,n):
        seg=C[i-p+1:i+1]; mu=m[i]; var=sum((x-mu)**2 for x in seg)/p; sd[i]=var**0.5
    sig=[0]*n
    for i in range(p,n):
        if sd[i] is None: continue
        up=m[i]+mult*sd[i]; dn=m[i]-mult*sd[i]
        if C[i]<dn: sig[i]=1
        elif C[i]>up: sig[i]=-1
    f=show(f"Boll{p}/{mult} revert", sig, sl_pts=30, tp_pts=0, trail_trig=25, trail_dist=8, max_bars=30, cooldown=5)
    best_overall.append((f"Boll{p}/{mult}",f['pnl']))

# ---- 5) RSI reversal ----
for lo,hi in [(30,70),(25,75),(20,80)]:
    sig=[0]*n
    for i in range(1,n):
        if r14[i] is None or r14[i-1] is None: continue
        if r14[i-1]<=lo and r14[i]>lo: sig[i]=1   # cross up out of oversold
        elif r14[i-1]>=hi and r14[i]<hi: sig[i]=-1
    f=show(f"RSI14 {lo}/{hi} revert", sig, sl_pts=30, tp_pts=60, trail_trig=30, trail_dist=10, max_bars=40, cooldown=3)
    best_overall.append((f"RSI{lo}/{hi}",f['pnl']))

# ---- 6) Supertrend follow ----
for mult in [2.0,3.0]:
    st,dr=supertrend(H,L,C,A14,mult)
    sig=[0]*n
    for i in range(1,n):
        if dr[i]!=dr[i-1] and dr[i]!=0:
            sig[i]=dr[i]
    f=show(f"Supertrend x{mult}", sig, sl_pts=40, tp_pts=0, trail_trig=40, trail_dist=15, max_bars=80)
    best_overall.append((f"Supertrend{mult}",f['pnl']))

# ---- 7) Opening Range Breakout (first 30m after 08:30 CT = 510) ----
sig=[0]*n
orh=orl=None; curday=None
for i in range(n):
    if DAY[i]!=curday:
        curday=DAY[i]; orh=orl=None
    # build OR during 510..539
    if 510<=TM[i]<540:
        orh = H[i] if orh is None else max(orh,H[i])
        orl = L[i] if orl is None else min(orl,L[i])
    elif TM[i]>=540 and orh is not None:
        if C[i]>orh: sig[i]=1
        elif C[i]<orl: sig[i]=-1
f=show("ORB 08:30-09:00 CT", sig, sl_pts=30, tp_pts=60, trail_trig=30, trail_dist=12, max_bars=60, cooldown=0)
best_overall.append(("ORB",f['pnl']))

print("\n=== RANKING (full-period PnL, pts) ===")
for name,p in sorted(best_overall,key=lambda x:-x[1]):
    flag=" <-- baseline" if name=="baseline_slope" else (" *** BEATS 2x" if p>=13696 else (" ** beats baseline" if p>6848 else ""))
    print(f"  {name:22s} {p:8.0f}{flag}")
