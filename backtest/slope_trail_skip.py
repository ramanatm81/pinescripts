#!/usr/bin/env python3
"""
Test: after a TRAIL exit, skip the next N would-be entry signals, then resume.
Sweep N = 0 (baseline), 1, 2. RAW and 1pt-slippage.

Rationale to check: trail exits are the whole edge (see slope_exit_breakdown.py).
Does the signal immediately AFTER a trailed winner tend to be a loser (mean the
move already ran)? If so, skipping it should raise net. If not, we're just
dropping trail winners and it hurts.
"""
import csv, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def load_5yr():
    bars = []
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o = float(row["open"]); h = float(row["high"])
                l = float(row["low"]); c = float(row["close"])
            except (ValueError, TypeError, KeyError):
                continue
            dt = datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt, o, h, l, c, dt.hour * 60 + dt.minute))
    return bars

def summarize(trades, slip):
    pnl = sum(t[3] - slip for t in trades)
    n = len(trades)
    wins = sum(1 for t in trades if (t[3] - slip) > 0)
    gw = sum((t[3] - slip) for t in trades if (t[3] - slip) > 0)
    gl = sum((t[3] - slip) for t in trades if (t[3] - slip) <= 0)
    pf = gw / abs(gl) if gl else float('inf')
    return dict(n=n, pnl=pnl, wr=(wins/n*100 if n else 0), pf=pf, avg=(pnl/n if n else 0))

if __name__ == "__main__":
    print("loading 5yr data...")
    bars = load_5yr()
    print(f"loaded {len(bars):,} bars, {bars[0][0]} -> {bars[-1][0]}\n")

    results = {}
    for N in (0, 1, 2):
        p = dict(BASE, skipAfterTrail=N)
        trades = bt.run(bars, p)
        results[N] = trades

    for slip in (0.0, 1.0):
        print(f"{'='*72}")
        print(f"POST-TRAIL SKIP SWEEP   (slippage = {slip} pt/round-turn)")
        print(f"{'='*72}")
        print(f"{'skip N':>7}{'trades':>9}{'net pnl':>12}{'win%':>8}{'PF':>7}{'avg':>8}"
              f"{'  vs baseline':>14}")
        print("-" * 72)
        base_pnl = None
        for N in (0, 1, 2):
            s = summarize(results[N], slip)
            if N == 0:
                base_pnl = s["pnl"]
                delta = ""
            else:
                d = s["pnl"] - base_pnl
                delta = f"{d:+.0f} ({d/base_pnl*100:+.1f}%)" if base_pnl else f"{d:+.0f}"
            print(f"{N:>7}{s['n']:>9}{s['pnl']:>12.0f}{s['wr']:>7.1f}%{s['pf']:>7.2f}"
                  f"{s['avg']:>8.1f}{delta:>16}")
        print()

    # exit-reason mix for each N (does skipping change WHAT we exit on?)
    print(f"{'='*72}\nEXIT-REASON MIX by skip N (RAW)\n{'='*72}")
    reasons = ["TRAIL", "TEXP", "TP", "SL", "THRD", "BLK", "EOD", "BE"]
    hdr = f"{'reason':<8}" + "".join(f"{'N='+str(N):>16}" for N in (0, 1, 2))
    print(hdr); print("-" * len(hdr))
    for r in reasons:
        row = f"{r:<8}"
        for N in (0, 1, 2):
            sub = [t for t in results[N] if t[4] == r]
            cnt = len(sub); pnl = sum(t[3] for t in sub)
            row += f"{cnt:>6}{pnl:>10.0f}"
        print(row)
