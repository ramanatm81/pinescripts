#!/usr/bin/env python3
"""Parameter sweep over the ported strategy. Writes ranked results to results.txt."""
import itertools, time, json
from backtest import load, run, stats

bars = load()
BASE = dict(slopeEntry=1.7, slAboveSma=50.0, slBelowSma=30.0, tpPts=40.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=10.0, trailDistStrong=10.0,
            tExpBars=30, tExpHardBars=20, tExpHardSlope=1.0)

base_stats = stats(run(bars, BASE))
print("BASELINE", base_stats)

# Sweep grid — focused on the highest-leverage knobs. Keep combos bounded.
grid = dict(
    slopeEntry   = [1.4, 1.7, 2.0, 2.5, 3.0],
    tpPts        = [30.0, 40.0, 50.0, 60.0],
    tpMult       = [2.0, 3.0, 4.0],
    trailTrigger = [20.0, 30.0, 40.0],
    trailDist    = [8.0, 10.0, 15.0],
    tExpBars     = [20, 30, 40],
    tExpHardBars = [15, 20, 30],
)
keys = list(grid.keys())
combos = list(itertools.product(*[grid[k] for k in keys]))
print(f"{len(combos)} combos")

results=[]
t0=time.time()
for i,combo in enumerate(combos):
    p = dict(BASE)
    for k,v in zip(keys,combo): p[k]=v
    s = stats(run(bars,p))
    results.append((s["pnl"], s["winrate"], s["n"], dict(zip(keys,combo))))
    if i%200==0:
        el=time.time()-t0
        print(f"{i}/{len(combos)} {el:.0f}s best_pnl={max(r[0] for r in results):.0f}")

results.sort(key=lambda r:-r[0])
with open("results.txt","w") as f:
    f.write(f"BASELINE {base_stats}\n\n")
    f.write("TOP 30 by PnL (pts):\n")
    for pnl,wr,n,params in results[:30]:
        f.write(f"pnl={pnl:8.1f} win={wr:5.1f}% n={n:4d}  {params}\n")
    f.write("\nTOP 20 by win-rate (min 150 trades):\n")
    for pnl,wr,n,params in sorted([r for r in results if r[2]>=150], key=lambda r:-r[1])[:20]:
        f.write(f"win={wr:5.1f}% pnl={pnl:8.1f} n={n:4d}  {params}\n")
print("done", time.time()-t0, "s -> results.txt")
print("TOP5:")
for r in results[:5]: print(r)
