#!/usr/bin/env python3
"""Push VWAP mean-reversion (the only classic with an edge here) — sweep entry
band, exit target/trail, ATR-normalized bands, RSI confirm, session filter."""
import itertools
from strategies import (load, ema, sma, atr, rsi, session_vwap, backtest_signals, stats)

d=load(); n=d["n"]; C=d["C"]; H=d["H"]; L=d["L"]; V=d["V"]; DAY=d["DAY"]; TM=d["TM"]
split=int(n*0.6)
def slc(a,b): return {k:(v[a:b] if isinstance(v,list) else v) for k,v in d.items()}|{"n":b-a}
def show(name,sig,**kw):
    f=stats(backtest_signals(d,sig,**kw))
    i=stats(backtest_signals(slc(0,split),sig[:split],**kw))
    o=stats(backtest_signals(slc(split,n),sig[split:],**kw))
    tag=" ***2x" if f['pnl']>=13696 else (" **beat" if f['pnl']>6848 else "")
    print(f"{name:40s} FULL {f['pnl']:8.0f} win{f['winrate']:3.0f}% n{f['n']:4d} pf{f['pf']:4.2f} | IS {i['pnl']:7.0f} | OOS {o['pnl']:7.0f} win{o['winrate']:3.0f}%{tag}")
    return f['pnl']

vwap=session_vwap(H,L,C,V,DAY)
A14=atr(H,L,C,14); r14=rsi(C,14)

best=[]
# ATR-normalized VWAP distance: enter when |C-vwap| >= k*ATR, fade back to vwap
for k in [1.0,1.5,2.0,2.5]:
    for tt,td in [(20,6),(25,8),(30,10)]:
        sig=[0]*n
        for i in range(n):
            if vwap[i] is None or A14[i] is None: continue
            dev=C[i]-vwap[i]; band=k*A14[i]
            if dev<=-band: sig[i]=1
            elif dev>=band: sig[i]=-1
        p=show(f"VWAP k{k}ATR trail{tt}/{td}", sig, sl_pts=35, tp_pts=0,
               trail_trig=tt, trail_dist=td, max_bars=30, cooldown=3)
        best.append((f"vwapK{k}_{tt}/{td}",p))

# add RSI confirmation (only fade when RSI also extreme)
for k in [1.5,2.0]:
    for rl,rh in [(35,65),(30,70)]:
        sig=[0]*n
        for i in range(n):
            if vwap[i] is None or A14[i] is None or r14[i] is None: continue
            dev=C[i]-vwap[i]; band=k*A14[i]
            if dev<=-band and r14[i]<=rl: sig[i]=1
            elif dev>=band and r14[i]>=rh: sig[i]=-1
        p=show(f"VWAP k{k}ATR + RSI{rl}/{rh}", sig, sl_pts=35, tp_pts=0,
               trail_trig=25, trail_dist=8, max_bars=30, cooldown=3)
        best.append((f"vwapK{k}_rsi{rl}",p))

# TP target instead of trail
for k in [1.5,2.0]:
    for tp in [30,50,80]:
        sig=[0]*n
        for i in range(n):
            if vwap[i] is None or A14[i] is None: continue
            dev=C[i]-vwap[i]; band=k*A14[i]
            if dev<=-band: sig[i]=1
            elif dev>=band: sig[i]=-1
        p=show(f"VWAP k{k}ATR TP{tp} (target=vwap-ish)", sig, sl_pts=35, tp_pts=tp,
               trail_trig=None, trail_dist=None, max_bars=30, cooldown=3)
        best.append((f"vwapK{k}_tp{tp}",p))

print("\nTOP:")
for nm,p in sorted(best,key=lambda x:-x[1])[:8]:
    print(f"  {nm:22s} {p:8.0f}")
