"""Run: both new session toggles ON (blockLunch, blockAsia) + fixed 50pt SL.
Reports PF, gross win/loss, win rate, per-year breakdown vs baseline."""
import backtest as bt
from collections import defaultdict

def full_stats(trades):
    n = len(trades)
    if n == 0:
        return dict(n=0)
    pnl = sum(t[3] for t in trades)
    wins = [t[3] for t in trades if t[3] > 0]
    losses = [t[3] for t in trades if t[3] <= 0]
    gp = sum(wins)
    gl = -sum(losses)  # positive
    pf = (gp / gl) if gl > 0 else float('inf')
    return dict(n=n, pnl=round(pnl, 1), winrate=round(len(wins)/n*100, 1),
                pf=round(pf, 3), gp=round(gp, 1), gl=round(gl, 1),
                avg=round(pnl/n, 2))

def per_year(trades):
    # trade tuple: [entry_time, exit_time?, ...]; t[0] is entry timestamp string
    buckets = defaultdict(list)
    for t in trades:
        yr = str(t[6])[:4]   # t[6] = dt (entry timestamp)
        buckets[yr].append(t)
    out = {}
    for yr in sorted(buckets):
        s = full_stats(buckets[yr])
        out[yr] = s
    return out

# Fukuoka snapshot params (matches live slope_strategy.pine defaults)
BASE_TRAIL = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True,
                  smaPeriod=9, slAboveSma=50.0, slBelowSma=30.0,
                  tpPts=50.0, tpMult=3.0, trailTrigger=30.0, trailDist=8.0,
                  trailDistStrong=10.0, tExpBars=20, tExpHardBars=20,
                  tExpHardSlope=1.0, cooldownBars=10, cooldownBarsRTH=10,
                  deepSlope=3.0)

bars = bt.load()
print(f"loaded {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}\n")

scenarios = {
    "BASELINE (defaults: lunch ON, asia OFF, SMA-SL)":
        dict(BASE_TRAIL),
    "REQUEST: lunch ON + asia ON + fixed 50pt SL":
        dict(BASE_TRAIL, blockLunch=True, blockAsia=True,
             enableSmaSL=False, slPts=50.0),
    "control: lunch+asia ON, SMA-SL (isolate SL effect)":
        dict(BASE_TRAIL, blockLunch=True, blockAsia=True),
    "control: fixed 50 SL, default sessions (isolate toggle effect)":
        dict(BASE_TRAIL, enableSmaSL=False, slPts=50.0),
}

for name, p in scenarios.items():
    tr = bt.run(bars, p)
    s = full_stats(tr)
    print(f"### {name}")
    print(f"    trades={s['n']}  net={s['pnl']}  win%={s['winrate']}  "
          f"PF={s['pf']}  (GP={s['gp']} / GL={s['gl']})  avg/trade={s['avg']}")
    print()

# Per-year for the requested config
print("=== PER-YEAR: REQUEST config (lunch+asia ON, fixed 50 SL) ===")
tr = bt.run(bars, dict(BASE_TRAIL, blockLunch=True, blockAsia=True,
                       enableSmaSL=False, slPts=50.0))
for yr, s in per_year(tr).items():
    print(f"  {yr}: trades={s['n']:>4}  net={s['pnl']:>9}  "
          f"win%={s['winrate']:>5}  PF={s['pf']}")
