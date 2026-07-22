#!/usr/bin/env python3
"""
Is the strategy decaying? Monthly + weekly net P&L over the 5yr set, with focus
on the tail (last 6 months). Also profiles LOSERS to find where to cut:
by hour-of-day (CT), by direction, by exit reason, by |entry slope| bucket,
and by activeSL size. Goal: find a loser cluster we can filter without killing trail winners.
"""
import csv, sys
from collections import defaultdict
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
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return bars

if __name__=="__main__":
    print("loading 5yr data..."); bars=load_5yr()
    print(f"loaded {len(bars):,} bars, {bars[0][0].date()} -> {bars[-1][0].date()}\n")
    trades = bt.run(bars, BASE)   # tuple: (dir, entry, exit, pnl, reason, deep, dt)
    print(f"{len(trades)} trades, net {sum(t[3] for t in trades):.0f} pts\n")

    # ---- monthly P&L ----
    monthly=defaultdict(lambda:[0.0,0])
    for t in trades:
        k=t[6].strftime("%Y-%m"); monthly[k][0]+=t[3]; monthly[k][1]+=1
    print("MONTHLY net P&L (pts):")
    cum=0
    for k in sorted(monthly):
        pnl,n=monthly[k]; cum+=pnl
        bar="#"*int(abs(pnl)/200)
        print(f"  {k}  {pnl:>8.0f}  ({n:>3} tr)  cum {cum:>8.0f}  {bar}")

    # ---- last 6 calendar months detail ----
    print("\nLAST 6 MONTHS by week (net pts):")
    last6=sorted(monthly)[-6:]
    weekly=defaultdict(lambda:[0.0,0,0])  # pnl, n, wins
    for t in trades:
        if t[6].strftime("%Y-%m") in last6:
            wk=t[6].strftime("%G-W%V"); weekly[wk][0]+=t[3]; weekly[wk][1]+=1
            if t[3]>0: weekly[wk][2]+=1
    for wk in sorted(weekly):
        pnl,n,w=weekly[wk]
        print(f"  {wk}  {pnl:>8.0f}  ({n:>3} tr, {w/n*100 if n else 0:>4.0f}% win)")

    def profile(title, keyfn, tr):
        print(f"\n{title}")
        agg=defaultdict(lambda:[0.0,0,0])  # pnl,n,wins
        for t in tr:
            k=keyfn(t); agg[k][0]+=t[3]; agg[k][1]+=1
            if t[3]>0: agg[k][2]+=1
        for k in sorted(agg):
            pnl,n,w=agg[k]
            print(f"  {str(k):<14} net {pnl:>8.0f}  ({n:>4} tr, {w/n*100 if n else 0:>4.0f}% win, avg {pnl/n if n else 0:>6.1f})")

    # loser profiling on the FULL set (structure is stable; helps design a cut)
    profile("BY HOUR (CT) — all trades:", lambda t: f"{t[6].hour:02d}:00", trades)
    profile("BY DIRECTION:", lambda t: "LONG" if t[0]==1 else "SHORT", trades)

    # entry slope magnitude bucket needs slope — not stored in tuple. Approx via exit reason instead.
    profile("BY EXIT REASON:", lambda t: t[4], trades)

    # ---- how do the LAST 6 months alone break down by hour & direction? ----
    tail=[t for t in trades if t[6].strftime("%Y-%m") in last6]
    print(f"\n--- LAST 6 MONTHS ONLY ({len(tail)} trades, net {sum(t[3] for t in tail):.0f}) ---")
    profile("  by hour (CT):", lambda t: f"{t[6].hour:02d}:00", tail)
    profile("  by direction:", lambda t: "LONG" if t[0]==1 else "SHORT", tail)
