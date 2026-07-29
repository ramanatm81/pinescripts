#!/usr/bin/env python3
"""
Hourly PnL breakdown, showing BOTH the CT hour (strategy-internal) and the
London hour (what the user reads off the chart) for each bucket. Lets us pin
down exactly which clock-hours carry the edge without timezone confusion.

London = CT + 6h in summer (America/Chicago CDT = UTC-5, Europe/London BST = UTC+1).
The port stamps dt in CT (UTC-5). London hour = (ct_hour + 6) % 24.
"""
import sys, os, importlib
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def hourly(trades, slip=0.0):
    by = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0, "gw": 0.0, "gl": 0.0})
    for (d, en, ex, pnl, reason, deep, dt) in trades:
        pnl -= slip
        b = by[dt.hour]
        b["n"] += 1; b["pnl"] += pnl
        if pnl > 0: b["wins"] += 1; b["gw"] += pnl
        else: b["gl"] += pnl
    return by

def report(trades, slip, label):
    by = hourly(trades, slip)
    tot_p = sum(b["pnl"] for b in by.values())
    print(f"\n{'='*74}\n{label}  (slip {slip})\n{'='*74}")
    print(f"{'CT':>3} {'LDN':>4} {'trades':>7} {'net':>8} {'%net':>7} {'win%':>7} {'avg':>7} {'PF':>6}")
    print("-" * 74)
    for ct in sorted(by):
        b = by[ct]
        ldn = (ct + 6) % 24
        pct = b["pnl"]/tot_p*100 if tot_p else 0
        wr = b["wins"]/b["n"]*100 if b["n"] else 0
        avg = b["pnl"]/b["n"] if b["n"] else 0
        pf = b["gw"]/abs(b["gl"]) if b["gl"] else 99.9
        print(f"{ct:>3} {ldn:>4} {b['n']:>7} {b['pnl']:>8.0f} {pct:>6.1f}% {wr:>6.1f}% {avg:>7.1f} {pf:>6.2f}")
    print("-" * 74)
    print(f"TOTAL       {sum(b['n'] for b in by.values()):>7} {tot_p:>8.0f}")

def run_file(path, name):
    os.environ["BACKTEST_DATA"] = path
    importlib.reload(bt)
    bars = bt.load()
    trades = bt.run(bars, BASE)
    print(f"\n######## {name}  ({len(trades)} trades) ########")
    report(trades, 1.0, f"{name} — 1pt slip (realistic)")

if __name__ == "__main__":
    run_file("/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv", "5-YEAR")
    run_file("/Users/maheshk81/Downloads/data.csv", "OOS")
