"""CHOSEN config: both session toggles ON (lunch+asia) + SMA-based SL.
Fukuoka base params. Reports PF, gross W/L, per-year, and a 1pt-slip floor."""
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

def slip_net(trades, slip):
    # each trade pays 'slip' pts (entry+exit modeled as one round-trip cost)
    return round(sum(t[3] for t in trades) - slip * len(trades), 1)

# Fukuoka base (matches live slope_strategy.pine) + both toggles ON, SMA-SL ON
CFG = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0,
           blockLunch=True, blockAsia=True)

bars = bt.load()
print(f"loaded {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}\n")

tr = bt.run(bars, CFG)
s = full_stats(tr)
print("### CHOSEN: lunch ON + asia ON + SMA-based SL")
print(f"    trades={s['n']}  net={s['pnl']}  win%={s['winrate']}  "
      f"PF={s['pf']}  (GP={s['gp']} / GL={s['gl']})  avg/trade={s['avg']}\n")

print("=== PER-YEAR ===")
for yr, ys in per_year(tr).items():
    print(f"  {yr}: trades={ys['n']:>4}  net={ys['pnl']:>9}  "
          f"win%={ys['winrate']:>5}  PF={ys['pf']}")

print("\n=== SLIPPAGE SENSITIVITY (net pts) ===")
for slip in (0.0, 0.5, 1.0, 2.0):
    print(f"  {slip}pt/trade slip -> net = {slip_net(tr, slip)}")

from collections import Counter
print("\nexit reasons:", Counter(t[4] for t in tr))
