#!/usr/bin/env python3
"""Port of slope_strategy_v2.pine (Support Ride, LONG only) for 5yr + OOS backtest.

Entry:  low in [support - ride, support + ride]  AND  support < resistance
        AND (resistance - support) <= maxSpread   AND not in a blocked session.
Exit:   broker TP limit  = entry + tpPts
        broker stop       = max(support - zoneWidth, entry - maxStopPts)   [tighter wins]
        EOD/session flatten (approximated: block windows don't force-close here; entries
        are simply suppressed in them — matches "no new entries" but NOT the .pine's
        in-window flatten. Trades opened before a block run to TP/stop; acceptable since
        v2's blocks are short. EOD flatten IS applied at ctm in [900,960).)

Fills: strategy default (calc_on_every_tick=false): entry fills NEXT bar open after the
signal bar; TP/stop are resting orders that fill intrabar (stop at level, or gap-open if
the bar gaps through). This matches the .pine broker behavior.

Fractals: ta.pivothigh/low(srHalfWidth, srHalfWidth) — strict greater/less on both sides,
confirmed srHalfWidth bars late. Same as backtest.py.
"""
import os, csv, sys, statistics as st
from datetime import datetime, timezone, timedelta

DATA = os.environ.get("BACKTEST_DATA",
                      os.path.join(os.path.dirname(__file__), "..", "ohlcv", "mnq_5yr.csv"))
CT = timezone(timedelta(hours=-5))   # America/Chicago (CDT); .pine uses hour(time,"America/Chicago")

# ---- params (defaults = current v2 .pine inputs) ----
P = dict(srHalfWidth=10, ride=5.0, zone=25.0, tp=20.0, maxStop=30.0,
         maxSpread=75.0, enableSpread=True,
         # session blocks (CT minutes) — .pine defaults: LNopen, preNY, lunch ON; NYopen, asia OFF
         blockLNOpen=True, blockPreNY=True, blockLunch=True, blockNYOpen=False, blockAsia=False)

def load(path):
    bars=[]
    with open(path) as f:
        for row in csv.DictReader(f):
            t=row["time"]
            if not t: continue
            try:
                o=float(row["open"]); h=float(row["high"]); l=float(row["low"]); c=float(row["close"])
            except (ValueError, TypeError): continue
            dt=datetime.fromisoformat(t).astimezone(CT)
            bars.append((dt, o,h,l,c, dt.hour*60+dt.minute, dt.year))
    return bars

def blocked(ctm, p):
    if 900<=ctm<960: return True                          # eodClose (always flatten window)
    if 1020<=ctm<1050: return True                        # ethOpen (hardcoded in .pine)
    if p["blockLNOpen"] and 120<=ctm<150: return True
    if p["blockPreNY"]  and 450<=ctm<540: return True
    if p["blockLunch"]  and 600<=ctm<780: return True
    if p["blockNYOpen"] and 510<=ctm<540: return True
    if p["blockAsia"]   and (ctm>=1320 or ctm<300): return True
    return False

def run(bars, p, slip=0.0):
    highs=[b[2] for b in bars]; lows=[b[3] for b in bars]; n=len(bars)
    w=p["srHalfWidth"]; RIDE=p["ride"]; ZONE=p["zone"]; TP=p["tp"]; MAXSL=p["maxStop"]
    lastFL=None; lastFH=None
    inpos=False; entry=esc=tp=None; pending=False; supp_sig=res_sig=None; ey=None
    trades=[]  # (pnl, year, reason, side, spread)
    for bi in range(n):
        dt,o,h,l,c,ctm,yr = bars[bi]
        # confirm pivots (strict, srHalfWidth late)
        if bi>=2*w:
            center=bi-w
            ch=highs[center]
            if all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1]):
                lastFH=ch
            cl=lows[center]
            if all(cl<x for x in lows[bi-2*w:center]) and all(cl<x for x in lows[center+1:bi+1]):
                lastFL=cl
        # execute pending entry at THIS bar's open
        if pending and not inpos:
            entry=o; inpos=True; esc=max(supp_sig-ZONE, entry-MAXSL); tp=entry+TP
            e_supp=supp_sig; e_res=res_sig; e_side=side_sig; ey=yr; pending=False
        # manage open position
        if inpos:
            # EOD flatten
            if 900<=ctm<960:
                trades.append((c-entry, ey, 'EOD', e_side, e_res-e_supp)); inpos=False; continue
            hit_stop = l<=esc; hit_tp = h>=tp
            if hit_stop:
                fill = o if o<esc else esc            # gap-through fills at open
                trades.append((fill-entry-slip, ey, 'ESC', e_side, e_res-e_supp)); inpos=False; continue
            if hit_tp:
                fill = o if o>tp else tp
                trades.append((fill-entry-slip, ey, 'TP', e_side, e_res-e_supp)); inpos=False; continue
        # entry signal (fills next bar open)
        if not inpos and not pending and lastFL is not None and lastFH is not None:
            lo_ok = (l>=lastFL-RIDE) and (l<=lastFL+RIDE)
            spread = lastFH-lastFL
            spread_ok = (not p["enableSpread"]) or (spread<=p["maxSpread"])
            if lastFL<lastFH and lo_ok and spread_ok and not blocked(ctm,p):
                pending=True; supp_sig=lastFL; res_sig=lastFH
                side_sig = 'above' if l>=lastFL else 'below'
    return trades

def summarize(trades, V=2.0, label=""):
    if not trades:
        print(f"{label}: no trades"); return
    n=len(trades); wins=[t for t in trades if t[0]>0]; net=sum(t[0] for t in trades)
    gp=sum(t[0] for t in wins); gl=-sum(t[0] for t in trades if t[0]<=0)
    pf=gp/gl if gl>0 else float('inf')
    print(f"\n{'='*64}\n{label}")
    print(f"  trades {n}   win% {100*len(wins)/n:.1f}   net {net:+.1f}pt = ${net*V:+,.0f}   PF {pf:.2f}")
    # per year
    yrs=sorted(set(t[1] for t in trades))
    print(f"  {'year':>6} {'trades':>7} {'win%':>6} {'net$':>10} {'PF':>5}")
    posyears=0
    for y in yrs:
        g=[t for t in trades if t[1]==y]; w=sum(1 for t in g if t[0]>0)
        ynet=sum(t[0] for t in g); ygp=sum(t[0] for t in g if t[0]>0); ygl=-sum(t[0] for t in g if t[0]<=0)
        ypf=ygp/ygl if ygl>0 else float('inf')
        if ynet>0: posyears+=1
        print(f"  {y:>6} {len(g):>7} {100*w/len(g):>6.1f} {ynet*V:>+10,.0f} {ypf:>5.2f}")
    print(f"  positive years: {posyears}/{len(yrs)}")

if __name__=="__main__":
    slip = float(sys.argv[1]) if len(sys.argv)>1 else 0.0
    print(f"DATA={DATA}\nparams={P}\nslippage per trade = {slip} pts")
    bars=load(DATA)
    print(f"loaded {len(bars)} bars  {bars[0][0].date()} → {bars[-1][0].date()}")
    tr=run(bars, P, slip=slip)
    summarize(tr, label=f"5YR  (slip={slip})")
