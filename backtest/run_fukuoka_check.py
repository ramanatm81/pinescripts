"""Reproduce Fukuoka baseline: both new toggles OFF + SMA-based SL.
Also runs with blockLNOpen/blockPreNY OFF to test the PURE original (no session
blocks at all), since those two default ON in the current file but may not have
been on in the original Fukuoka measurement."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
from collections import defaultdict

def full_stats(trades):
    n = len(trades)
    if n == 0:
        return dict(n=0, pnl=0, winrate=0, pf=0, gp=0, gl=0, avg=0)
    pnl = sum(t[3] for t in trades)
    wins = [t[3] for t in trades if t[3] > 0]
    losses = [t[3] for t in trades if t[3] <= 0]
    gp, gl = sum(wins), -sum(losses)
    pf = (gp / gl) if gl > 0 else float('inf')
    return dict(n=n, pnl=round(pnl, 1), winrate=round(len(wins)/n*100, 1),
                pf=round(pf, 3), gp=round(gp, 1), gl=round(gl, 1),
                avg=round(pnl/n, 2))

def per_year(trades):
    b = defaultdict(list)
    for t in trades:
        b[str(t[6])[:4]].append(t)
    return {y: full_stats(b[y]) for y in sorted(b)}

# Fukuoka base params (match live slope_strategy.pine defaults)
FUKUOKA = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
               slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
               trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
               tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
               cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

bars = bt.load()
print(f"loaded {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}\n")

scenarios = {
    "Fukuoka, new toggles OFF, current session blocks (LN+PreNY ON)":
        dict(FUKUOKA, blockLunch=False, blockAsia=False),
    "Fukuoka, ALL session blocks OFF (purest original)":
        dict(FUKUOKA, blockLunch=False, blockAsia=False,
             blockLNOpen=False, blockPreNY=False, blockNYOpen=False),
}

for name, p in scenarios.items():
    tr = bt.run(bars, p)
    s = full_stats(tr)
    print(f"### {name}")
    print(f"    trades={s['n']}  net={s['pnl']}  win%={s['winrate']}  "
          f"PF={s['pf']}  (GP={s['gp']} / GL={s['gl']})  avg/trade={s['avg']}")
    for yr, ys in per_year(tr).items():
        print(f"      {yr}: n={ys['n']:>4}  net={ys['pnl']:>9}  "
              f"win%={ys['winrate']:>5}  PF={ys['pf']}")
    print()
