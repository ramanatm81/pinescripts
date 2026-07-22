#!/usr/bin/env python3
"""
Break down slope-strategy P&L by EXIT TYPE over the 5yr MNQ data, to answer:
how much of the strategy's profit comes from TRAIL exits vs everything else
(TP, SL, TEXP, THRD, BLK, EOD, BE)?

Uses the faithful port in backtest.py. Each trade tuple is
(dir, entry, exit, pnl, reason, deep, dt). We bucket by reason[4] and sum pnl[3].
RAW (0 slippage) to match the Fukuoka headline, plus a 1pt-slippage view since
the slope edge is known to be slippage-sensitive.
"""
import csv, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

# current slope_strategy.pine defaults
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

def breakdown(trades, slip=0.0):
    """Group by exit reason. slip = points shaved off every trade's pnl (round-turn)."""
    by = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0})
    for (d, en, ex, pnl, reason, deep, dt) in trades:
        pnl = pnl - slip
        b = by[reason]
        b["n"] += 1
        b["pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
            b["gross_win"] += pnl
        else:
            b["gross_loss"] += pnl
    return by

def report(trades, slip, label):
    by = breakdown(trades, slip)
    total_pnl = sum(b["pnl"] for b in by.values())
    total_n = sum(b["n"] for b in by.values())
    gross_win = sum(b["gross_win"] for b in by.values())
    gross_loss = sum(b["gross_loss"] for b in by.values())

    print(f"\n{'='*78}\n{label}   (slippage = {slip} pt/round-turn)\n{'='*78}")
    print(f"{'exit':<8}{'trades':>8}{'net pnl':>12}{'% of net':>10}{'win%':>8}"
          f"{'avg':>9}{'gross+':>12}{'gross-':>12}")
    print("-" * 78)
    # sort by net pnl descending so the biggest contributors are on top
    for reason in sorted(by, key=lambda r: by[r]["pnl"], reverse=True):
        b = by[reason]
        pct = (b["pnl"] / total_pnl * 100) if total_pnl else 0
        wr = (b["wins"] / b["n"] * 100) if b["n"] else 0
        avg = b["pnl"] / b["n"] if b["n"] else 0
        print(f"{reason:<8}{b['n']:>8}{b['pnl']:>12.0f}{pct:>9.1f}%{wr:>7.1f}%"
              f"{avg:>9.1f}{b['gross_win']:>12.0f}{b['gross_loss']:>12.0f}")
    print("-" * 78)
    print(f"{'TOTAL':<8}{total_n:>8}{total_pnl:>12.0f}{100.0:>9.1f}%"
          f"{'':>8}{total_pnl/total_n if total_n else 0:>9.1f}"
          f"{gross_win:>12.0f}{gross_loss:>12.0f}")
    pf = gross_win / abs(gross_loss) if gross_loss else float('inf')
    print(f"profit factor = {pf:.2f}")

    # ---- the ratio the user asked for: TRAIL profit vs the rest ----
    trail = by.get("TRAIL", {"pnl": 0.0, "gross_win": 0.0, "n": 0})
    trail_pnl = trail["pnl"]
    other_pnl = total_pnl - trail_pnl
    print(f"\n  TRAIL net       : {trail_pnl:>10.0f} pts  ({trail['n']} trades)")
    print(f"  ALL OTHER net   : {other_pnl:>10.0f} pts")
    if other_pnl != 0:
        print(f"  TRAIL : OTHER   : {trail_pnl/other_pnl:>10.2f}  (trail profit per 1 pt of other-exit profit)")
    if total_pnl:
        print(f"  TRAIL % of net  : {trail_pnl/total_pnl*100:>9.1f}%")
    if gross_win:
        print(f"  TRAIL % of gross winnings : {trail['gross_win']/gross_win*100:>6.1f}%")

if __name__ == "__main__":
    print("loading 5yr data...")
    bars = load_5yr()
    print(f"loaded {len(bars):,} bars, {bars[0][0]} -> {bars[-1][0]}")
    trades = bt.run(bars, BASE)
    print(f"{len(trades)} trades")
    report(trades, 0.0, "5YR EXIT BREAKDOWN — RAW")
    report(trades, 1.0, "5YR EXIT BREAKDOWN — 1pt slippage")
