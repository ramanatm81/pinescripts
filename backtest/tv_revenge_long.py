#!/usr/bin/env python3
"""
Rule: after a SHORT trade FAILS (closes at a loss), block LONG entries that
would fire within 20 minutes of that short's exit. Long allowed after 20 min.

Q1. How many such "revenge long" trades exist (baseline, rule OFF)?
Q2. What is their W/L and net PnL? (would removing them help?)
Q3. What is the full-strategy net effect of turning the rule ON?

Trade tuple: (dir, entry, exit, pnl, reason, deep, dt_close, dt_entry)
Trades are chronological and non-overlapping (single position).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

WINDOW_MIN = 20

def base_params():
    return dict(slopeEntry=1.7, slAboveSma=50.0, slBelowSma=30.0, tpPts=40.0, tpMult=3.0,
                trailTrigger=30.0, trailDist=10.0, trailDistStrong=10.0,
                tExpBars=30, tExpHardBars=20, tExpHardSlope=1.0)

def summ(label, tr):
    n=len(tr)
    if n==0:
        print(f"{label}: 0 trades"); return
    pnl=sum(t[3] for t in tr); wins=sum(1 for t in tr if t[3]>0)
    print(f"{label}: n={n}  pnl={pnl:+.1f}  win={wins}/{n}={wins/n*100:.1f}%  avg={pnl/n:+.3f}")

def main():
    bars = bt.load()
    print(f"loaded {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}\n")

    # ---- Baseline (rule OFF) ----
    base = bt.run(bars, base_params())
    summ("BASELINE (rule OFF)", base)

    # ---- Q1/Q2: identify revenge longs in the BASELINE sequence ----
    # For each trade, if it's a LONG whose ENTRY time is within WINDOW_MIN minutes
    # after the EXIT of a PRIOR SHORT that closed at a loss, flag it.
    # We scan back to the most recent losing short before this long's entry.
    from datetime import timedelta
    revenge=[]
    last_losing_short_exit=None
    for t in base:
        d, entry, exit_, pnl, reason, deep, dtc, dte = t
        if d==1:  # long
            if last_losing_short_exit is not None and dte is not None:
                gap = (dte - last_losing_short_exit).total_seconds()/60.0
                if 0 <= gap < WINDOW_MIN:
                    revenge.append((gap, t))
        # update the "most recent losing short exit" marker
        if d==-1 and pnl < 0:
            last_losing_short_exit = dtc
        # note: a losing short followed by another losing short just moves the marker;
        # a winning short does NOT arm the window (only failed shorts count).

    print(f"\nQ1. Revenge-longs (long entered <{WINDOW_MIN}min after a FAILED short): "
          f"{len(revenge)}  ({len(revenge)/len(base)*100:.1f}% of all trades)")
    rev_trades=[r[1] for r in revenge]
    summ("Q2. those revenge-longs only", rev_trades)
    # breakdown of their outcomes
    rwins=[t for t in rev_trades if t[3]>0]; rloss=[t for t in rev_trades if t[3]<=0]
    if rev_trades:
        wpnl=sum(t[3] for t in rwins); lpnl=sum(t[3] for t in rloss)
        print(f"    winners: {len(rwins)}  (+{wpnl:.1f})   losers: {len(rloss)}  ({lpnl:.1f})")
        gaps=[r[0] for r in revenge]
        print(f"    entry-gap after failed short: min={min(gaps):.0f} med={sorted(gaps)[len(gaps)//2]:.0f} max={max(gaps):.0f} min")

    # ---- Q3: full-strategy effect of the rule ON (blocking changes downstream state) ----
    out={}
    p=base_params(); p["revengeLongBlockMin"]=WINDOW_MIN; p["_out"]=out
    ruled = bt.run(bars, p)
    print()
    summ(f"RULE ON (block longs {WINDOW_MIN}min after failed short)", ruled)
    print(f"    longs actually suppressed by rule: {out.get('revengeBlockedCount')}")
    d_n=len(ruled)-len(base)
    d_pnl=sum(t[3] for t in ruled)-sum(t[3] for t in base)
    print(f"    delta vs baseline: trades {d_n:+d}   pnl {d_pnl:+.1f}")

if __name__ == "__main__":
    main()
