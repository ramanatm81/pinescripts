#!/usr/bin/env python3
"""
Anatomy of the slope-strategy edge: is +13k/5yr a real per-trade edge, or a
thin coin-flip carried by a fat right tail + zero slippage?

Reports:
  - per-trade expectancy, and what it becomes at 0.5 / 1.0 / 1.5 pt round-trip slip
  - contribution of the top-N winners to total PnL
  - PnL with the best 1% / 5% of trades removed (tail dependence)
  - yearly breakdown (is it every year, or a few good ones?)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
from collections import defaultdict

def base_params():
    return dict(slopeEntry=1.7, slAboveSma=50.0, slBelowSma=30.0, tpPts=40.0, tpMult=3.0,
                trailTrigger=30.0, trailDist=10.0, trailDistStrong=10.0,
                tExpBars=30, tExpHardBars=20, tExpHardSlope=1.0)

def main():
    bars = bt.load()
    tr = bt.run(bars, base_params())
    n=len(tr); pnls=sorted(t[3] for t in tr)
    total=sum(pnls)
    print(f"trades={n}  total={total:+.1f}  avg={total/n:+.4f} pts/trade\n")

    # --- slippage sensitivity (round-trip pts charged per trade) ---
    print("slippage sensitivity (per-trade round-trip cost):")
    for slip in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
        net=total - slip*n
        print(f"  {slip:>4.2f} pt slip -> net {net:+9.1f}  ({'PROFIT' if net>0 else 'LOSS'})")

    # --- tail dependence ---
    print("\ntail dependence (remove best trades):")
    for frac in (0.001, 0.005, 0.01, 0.05):
        k=max(1,int(n*frac))
        removed=sum(pnls[-k:])
        print(f"  remove top {frac*100:>4.1f}% ({k:>4d} trades, {removed:+.0f} pts) -> "
              f"remaining {total-removed:+9.1f}")

    # top-N winner contribution
    print("\nwinner concentration:")
    for k in (10, 50, 100, 500):
        print(f"  top {k:>4d} winners = {sum(pnls[-k:]):+.0f} pts "
              f"({sum(pnls[-k:])/total*100:.0f}% of total)")

    # --- yearly breakdown ---
    print("\nyearly (by exit year):")
    yr=defaultdict(lambda:[0,0.0])
    for t in tr:
        y=t[6].year
        yr[y][0]+=1; yr[y][1]+=t[3]
    for y in sorted(yr):
        c,p=yr[y]
        print(f"  {y}: {c:>5d} trades  {p:+9.1f} pts  ({p/c:+.3f}/trade)")

if __name__=="__main__":
    main()
