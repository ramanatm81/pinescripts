"""5-YEAR impact of the new toggles vs Fukuoka-as-shipped.
Fukuoka base. Compares toggles OFF vs BOTH ON, per-year, and shows exactly what
the toggles remove (net/PF of trades inside lunch+asia windows)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
from datetime import timezone, timedelta
from collections import defaultdict

def stats(trades):
    n = len(trades)
    if n == 0: return dict(n=0, pnl=0, winrate=0, pf=0, avg=0)
    pnl = sum(t[3] for t in trades)
    wins = [t[3] for t in trades if t[3] > 0]
    gl = -sum(t[3] for t in trades if t[3] <= 0)
    pf = (sum(wins)/gl) if gl > 0 else float('inf')
    return dict(n=n, pnl=round(pnl,1), winrate=round(len(wins)/n*100,1),
                pf=round(pf,3), avg=round(pnl/n,2))

def per_year(trades):
    b = defaultdict(list)
    for t in trades: b[str(t[6])[:4]].append(t)
    return {y: stats(b[y]) for y in sorted(b)}

def ctmin(dt):
    ct = dt.astimezone(timezone(timedelta(hours=-5)))
    return ct.hour*60 + ct.minute

FUK = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

bars = bt.load()
print(f"5YR: {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}\n")

off = bt.run(bars, dict(FUK, blockLunch=False, blockAsia=False))
on  = bt.run(bars, dict(FUK, blockLunch=True,  blockAsia=True))
so, sn = stats(off), stats(on)

print("### Fukuoka-as-shipped (toggles OFF)")
print(f"    n={so['n']}  net={so['pnl']}  win%={so['winrate']}  PF={so['pf']}  avg={so['avg']}")
print("### BOTH toggles ON")
print(f"    n={sn['n']}  net={sn['pnl']}  win%={sn['winrate']}  PF={sn['pf']}  avg={sn['avg']}")
print(f"\nIMPACT: net {sn['pnl']-so['pnl']:+.1f}   trades {sn['n']-so['n']:+d}   "
      f"PF {so['pf']}->{sn['pf']}   avg {so['avg']}->{sn['avg']}")

# what the toggles remove (from OFF set)
lunch = [t for t in off if 600 <= ctmin(t[6]) < 780]
asia  = [t for t in off if (ctmin(t[6]) >= 1320 or ctmin(t[6]) < 300)]
sl, sa = stats(lunch), stats(asia)
print(f"\n=== trades REMOVED by toggles (from OFF set) ===")
print(f"  lunch (10-13 CT): n={sl['n']}  net={sl['pnl']}  win%={sl['winrate']}  PF={sl['pf']}")
print(f"  asia  (22-05 CT): n={sa['n']}  net={sa['pnl']}  win%={sa['winrate']}  PF={sa['pf']}")
print(f"  combined removed: net={round(sl['pnl']+sa['pnl'],1)}  (this is the net the toggles delete)")

print("\n=== PER-YEAR: OFF vs ON ===")
py_off, py_on = per_year(off), per_year(on)
print(f"{'yr':>5} | {'OFF net':>9} {'PF':>6} | {'ON net':>9} {'PF':>6} | {'delta':>8}")
for yr in sorted(set(py_off)|set(py_on)):
    o = py_off.get(yr, dict(pnl=0,pf=0)); n = py_on.get(yr, dict(pnl=0,pf=0))
    print(f"{yr:>5} | {o['pnl']:>9} {o['pf']:>6} | {n['pnl']:>9} {n['pf']:>6} | {n['pnl']-o['pnl']:>+8.1f}")
