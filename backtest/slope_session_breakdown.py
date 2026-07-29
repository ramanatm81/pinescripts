#!/usr/bin/env python3
"""
Slope-strategy P&L bucketed by TRADING SESSION (by entry time), for both the
5yr MNQ history and the OOS export. DESCRIPTIVE stat only — safe per
[[port-mismodels-trail-tail]]: trade counts + win% are exact; net-pnl per
bucket leans on the trail tail, so treat absolute pnl as directional.

Trade tuple from bt.run(): (dir, entry, exit, pnl, reason, deep, dt).
dt is a tz-aware datetime already normalized to America/Chicago (UTC-5) by the
port's loader, so dt.hour is CT hour-of-day.

Sessions (CT, matching the strategy's internal Chicago anchoring):
  ASIA    17:00-01:59  (ETH open through Asia)
  LONDON  02:00-07:59  (London / pre-US)
  NY_AM   08:00-11:59  (US cash open, RTH morning)
  NY_PM   12:00-15:59  (RTH afternoon)
  CLOSE   16:00-16:59  (RTH close / maintenance edge)
"""
import sys
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def session_of(ct_hour):
    if 17 <= ct_hour <= 23 or ct_hour <= 1:
        return "ASIA   17-02"
    if 2 <= ct_hour <= 7:
        return "LONDON 02-08"
    if 8 <= ct_hour <= 11:
        return "NY_AM  08-12"
    if 12 <= ct_hour <= 15:
        return "NY_PM  12-16"
    return "CLOSE  16-17"

ORDER = ["ASIA   17-02", "LONDON 02-08", "NY_AM  08-12", "NY_PM  12-16", "CLOSE  16-17"]

def bucket(trades, slip=0.0):
    by = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0, "gw": 0.0, "gl": 0.0})
    for (d, en, ex, pnl, reason, deep, dt) in trades:
        pnl -= slip
        b = by[session_of(dt.hour)]
        b["n"] += 1
        b["pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1; b["gw"] += pnl
        else:
            b["gl"] += pnl
    return by

def report(trades, slip, label):
    by = bucket(trades, slip)
    tot_n = sum(b["n"] for b in by.values())
    tot_p = sum(b["pnl"] for b in by.values())
    tgw = sum(b["gw"] for b in by.values())
    tgl = sum(b["gl"] for b in by.values())
    print(f"\n{'='*80}\n{label}   (slippage {slip} pt/round-turn)\n{'='*80}")
    print(f"{'session':<14}{'trades':>8}{'net pts':>10}{'%net':>8}{'win%':>8}"
          f"{'avg':>8}{'PF':>7}{'gross+':>11}{'gross-':>11}")
    print("-" * 80)
    for s in ORDER:
        if s not in by:
            continue
        b = by[s]
        pct = b["pnl"] / tot_p * 100 if tot_p else 0
        wr = b["wins"] / b["n"] * 100 if b["n"] else 0
        avg = b["pnl"] / b["n"] if b["n"] else 0
        pf = b["gw"] / abs(b["gl"]) if b["gl"] else float("inf")
        pfs = f"{pf:.2f}" if pf != float("inf") else "inf"
        print(f"{s:<14}{b['n']:>8}{b['pnl']:>10.0f}{pct:>7.1f}%{wr:>7.1f}%"
              f"{avg:>8.1f}{pfs:>7}{b['gw']:>11.0f}{b['gl']:>11.0f}")
    print("-" * 80)
    pf = tgw / abs(tgl) if tgl else float("inf")
    print(f"{'TOTAL':<14}{tot_n:>8}{tot_p:>10.0f}{100.0:>7.1f}%"
          f"{'':>8}{tot_p/tot_n if tot_n else 0:>8.1f}{pf:>7.2f}{tgw:>11.0f}{tgl:>11.0f}")

def loss_report(trades, label):
    """LOSERS only — bucketed by session. slip-independent (a loss is a loss);
    counts + avg-loss + worst are exact and don't hinge on the trail tail."""
    by = defaultdict(lambda: {"n": 0, "loss": 0.0, "worst": 0.0, "total": 0})
    for (d, en, ex, pnl, reason, deep, dt) in trades:
        s = session_of(dt.hour)
        by[s]["total"] += 1
        if pnl < 0:
            by[s]["n"] += 1
            by[s]["loss"] += pnl
            by[s]["worst"] = min(by[s]["worst"], pnl)
    tot_n = sum(b["n"] for b in by.values())
    tot_l = sum(b["loss"] for b in by.values())
    tot_all = sum(b["total"] for b in by.values())
    print(f"\n{'='*80}\n{label} — LOSING TRADES by session\n{'='*80}")
    print(f"{'session':<14}{'losers':>8}{'loss%':>8}{'net loss':>11}{'%loss':>8}"
          f"{'avgloss':>9}{'worst':>8}")
    print("-" * 80)
    for s in ORDER:
        if s not in by:
            continue
        b = by[s]
        lr = b["n"] / b["total"] * 100 if b["total"] else 0
        pct = b["loss"] / tot_l * 100 if tot_l else 0
        avg = b["loss"] / b["n"] if b["n"] else 0
        print(f"{s:<14}{b['n']:>8}{lr:>7.1f}%{b['loss']:>11.0f}{pct:>7.1f}%"
              f"{avg:>9.1f}{b['worst']:>8.0f}")
    print("-" * 80)
    lr = tot_n / tot_all * 100 if tot_all else 0
    print(f"{'TOTAL':<14}{tot_n:>8}{lr:>7.1f}%{tot_l:>11.0f}{100.0:>7.1f}%"
          f"{tot_l/tot_n if tot_n else 0:>9.1f}")

def run_file(path, name):
    import os
    os.environ["BACKTEST_DATA"] = path
    import importlib
    importlib.reload(bt)
    bars = bt.load()
    print(f"\n######## {name} ########")
    print(f"loaded {len(bars):,} bars, {bars[0][0]} -> {bars[-1][0]}")
    trades = bt.run(bars, BASE)
    print(f"{len(trades)} trades")
    report(trades, 0.0, f"{name} — RAW (0 slip)")
    report(trades, 1.0, f"{name} — 1pt slippage")
    loss_report(trades, name)

if __name__ == "__main__":
    run_file("/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv", "5-YEAR (2021-06 .. 2026-06)")
    run_file("/Users/maheshk81/Downloads/data.csv", "OOS (data.csv)")
