#!/usr/bin/env python3
"""
Multi-strategy 1-minute backtester for NQ/MNQ (independent of slope_strategy).
Loads the same ~/Downloads/data.csv, computes standard indicators, and runs a
library of well-known intraday strategies through a common exit engine
(ATR/point stop + target + optional trail + time-based session flat).

Goal: find a rule set that beats the slope baseline (+6848 pts) by 2x on the
full dataset with an in-sample/out-of-sample split (no overfit).

PnL in POINTS. Uses stdlib only (run with /usr/bin/python3).
"""
import csv, math
from datetime import datetime, timezone, timedelta

DATA = "/Users/maheshk81/Downloads/data.csv"

def load():
    O=[];H=[];L=[];C=[];V=[];TM=[];DAY=[]
    with open(DATA) as f:
        for row in csv.DictReader(f):
            t=row["time"]
            if not t: continue
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
                v=float(row.get("Volume") or row.get("volume") or 0)
            except (ValueError,TypeError): continue
            dt=datetime.fromisoformat(t).astimezone(timezone(timedelta(hours=-5)))  # Chicago
            O.append(o);H.append(h);L.append(l);C.append(c);V.append(v)
            TM.append(dt.hour*60+dt.minute); DAY.append(dt.toordinal())
    return dict(O=O,H=H,L=L,C=C,V=V,TM=TM,DAY=DAY,n=len(C))

# ---------- indicators (all causal, no lookahead) ----------
def ema(x, p):
    out=[None]*len(x); k=2/(p+1); e=None
    for i,v in enumerate(x):
        e = v if e is None else v*k + e*(1-k)
        out[i]=e
    return out

def sma(x,p):
    out=[None]*len(x); s=0.0
    for i,v in enumerate(x):
        s+=v
        if i>=p: s-=x[i-p]
        if i>=p-1: out[i]=s/p
    return out

def atr(H,L,C,p):
    tr=[0.0]*len(C)
    for i in range(len(C)):
        if i==0: tr[i]=H[i]-L[i]
        else: tr[i]=max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
    # Wilder smoothing
    out=[None]*len(C); a=None
    for i,v in enumerate(tr):
        a = v if a is None else (a*(p-1)+v)/p
        out[i]= a if i>=p-1 else None
    return out

def rsi(C,p):
    out=[None]*len(C); ag=al=None
    for i in range(1,len(C)):
        ch=C[i]-C[i-1]; g=max(ch,0); ls=max(-ch,0)
        if ag is None: ag=g; al=ls
        else: ag=(ag*(p-1)+g)/p; al=(al*(p-1)+ls)/p
        if i>=p:
            rs= ag/al if al>1e-9 else 999
            out[i]=100-100/(1+rs)
    return out

def rolling_max(x,p):
    out=[None]*len(x)
    from collections import deque
    dq=deque()
    for i,v in enumerate(x):
        while dq and x[dq[-1]]<=v: dq.pop()
        dq.append(i)
        if dq[0]<=i-p: dq.popleft()
        if i>=p-1: out[i]=x[dq[0]]
    return out

def rolling_min(x,p):
    out=[None]*len(x)
    from collections import deque
    dq=deque()
    for i,v in enumerate(x):
        while dq and x[dq[-1]]>=v: dq.pop()
        dq.append(i)
        if dq[0]<=i-p: dq.popleft()
        if i>=p-1: out[i]=x[dq[0]]
    return out

def session_vwap(H,L,C,V,DAY):
    """VWAP reset each calendar day (Chicago ordinal)."""
    out=[None]*len(C); cumpv=0.0; cumv=0.0; cur=None
    for i in range(len(C)):
        if DAY[i]!=cur:
            cur=DAY[i]; cumpv=0.0; cumv=0.0
        tp=(H[i]+L[i]+C[i])/3
        cumpv+=tp*max(V[i],1); cumv+=max(V[i],1)
        out[i]=cumpv/cumv
    return out

def supertrend(H,L,C,atrv,mult):
    n=len(C); st=[None]*n; dir=[0]*n
    ub=lb=None; prev_st=None; prev_dir=1
    for i in range(n):
        if atrv[i] is None:
            continue
        hl2=(H[i]+L[i])/2
        bub=hl2+mult*atrv[i]; blb=hl2-mult*atrv[i]
        if ub is None: ub=bub; lb=blb
        ub = bub if (bub<ub or C[i-1]>ub) else ub
        lb = blb if (blb>lb or C[i-1]<lb) else lb
        if prev_st is None:
            prev_st=ub; prev_dir=-1
        if prev_dir==-1 and C[i]>ub: prev_dir=1
        elif prev_dir==1 and C[i]<lb: prev_dir=-1
        prev_st = lb if prev_dir==1 else ub
        st[i]=prev_st; dir[i]=prev_dir
    return st,dir

# ---------- common exit engine ----------
def backtest_signals(d, entries, sl_pts, tp_pts, trail_trig=None, trail_dist=None,
                     eod_flat=True, cooldown=0, max_bars=None):
    """
    entries[i] in {+1 long, -1 short, 0 none} — the signal to OPEN on bar i's close.
    Exits: hard SL / TP (intrabar, SL checked first), optional trail, time-based
    max_bars, EOD flat (15:00-16:00 CT). One position at a time. Fills at close of
    signal bar (bar-close model).
    """
    O,H,L,C,TM=d["O"],d["H"],d["L"],d["C"],d["TM"]
    n=d["n"]; pos=0; entry=0.0; best=0.0; trail=None; bars=0; cd=0
    trades=[]
    for i in range(n):
        eod = 15*60<=TM[i]<16*60
        # manage open position on THIS bar (using its H/L)
        if pos!=0:
            exited=False
            # SL
            if pos==1 and L[i]<=entry-sl_pts:
                trades.append(-sl_pts); pos=0; exited=True
            elif pos==-1 and H[i]>=entry+sl_pts:
                trades.append(-sl_pts); pos=0; exited=True
            # TP
            if not exited and tp_pts:
                if pos==1 and H[i]>=entry+tp_pts: trades.append(tp_pts); pos=0; exited=True
                elif pos==-1 and L[i]<=entry-tp_pts: trades.append(tp_pts); pos=0; exited=True
            # trail
            if not exited and trail_trig:
                if pos==1:
                    best=max(best,H[i])
                    if best-entry>=trail_trig:
                        t=best-trail_dist; trail=t if trail is None else max(trail,t)
                    if trail is not None and L[i]<=trail: trades.append(trail-entry); pos=0; exited=True
                else:
                    best=min(best,L[i])
                    if entry-best>=trail_trig:
                        t=best+trail_dist; trail=t if trail is None else min(trail,t)
                    if trail is not None and H[i]>=trail: trades.append(entry-trail); pos=0; exited=True
            if not exited:
                bars+=1
                if max_bars and bars>=max_bars:
                    trades.append((C[i]-entry) if pos==1 else (entry-C[i])); pos=0; exited=True
            if not exited and eod:
                trades.append((C[i]-entry) if pos==1 else (entry-C[i])); pos=0; exited=True
            if exited: cd=cooldown
        if cd>0 and pos==0: cd-=1
        # open on signal (not during eod)
        if pos==0 and cd==0 and not eod and entries[i]!=0:
            pos=entries[i]; entry=C[i]; best=C[i]; trail=None; bars=0
    return trades

def stats(trades):
    n=len(trades)
    if n==0: return dict(n=0,pnl=0.0,win=0,winrate=0.0,pf=0.0)
    pnl=sum(trades); w=sum(1 for t in trades if t>0)
    gp=sum(t for t in trades if t>0); gl=-sum(t for t in trades if t<0)
    return dict(n=n,pnl=round(pnl,1),wins=w,winrate=round(w/n*100,1),
                avg=round(pnl/n,2), pf=round(gp/gl,2) if gl>0 else 999)

if __name__=="__main__":
    d=load()
    print("bars",d["n"])
    # quick smoke test: EMA crossover
    e9=ema(d["C"],9); e21=ema(d["C"],21)
    sig=[0]*d["n"]
    for i in range(1,d["n"]):
        if e9[i] and e21[i] and e9[i-1] and e21[i-1]:
            if e9[i-1]<=e21[i-1] and e9[i]>e21[i]: sig[i]=1
            elif e9[i-1]>=e21[i-1] and e9[i]<e21[i]: sig[i]=-1
    tr=backtest_signals(d,sig,sl_pts=30,tp_pts=60,trail_trig=30,trail_dist=10)
    print("EMA9/21 cross smoke:",stats(tr))
