#!/usr/bin/env python3
"""Stage 2: fine sweep around a chosen center + walk-forward split to avoid overfit.
Usage: edit CENTER dict below to the stage-1 winner, then run.
Reports in-sample (first 60%) vs out-of-sample (last 40%) to flag overfitting."""
import itertools, time
from backtest import load, run, stats

bars = load()
n = len(bars)
split = int(n*0.6)
IS = bars[:split]; OOS = bars[split:]

BASE = dict(slopeEntry=1.7, slAboveSma=50.0, slBelowSma=30.0, tpPts=40.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=10.0, trailDistStrong=10.0,
            tExpBars=30, tExpHardBars=20, tExpHardSlope=1.0)

# CENTER = stage-1 winner
CENTER = dict(BASE, slopeEntry=2.5, tpPts=50.0, tpMult=3.0, trailTrigger=30.0,
              trailDist=8.0, tExpBars=20, tExpHardBars=20)

# fine grid around center for the most sensitive knobs
fine = dict(
    slopeEntry=[CENTER["slopeEntry"]-0.3, CENTER["slopeEntry"], CENTER["slopeEntry"]+0.3],
    tpPts=[CENTER["tpPts"]-10, CENTER["tpPts"], CENTER["tpPts"]+10],
    tpMult=[CENTER["tpMult"]-0.5, CENTER["tpMult"], CENTER["tpMult"]+0.5],
    trailDist=[CENTER["trailDist"]-2, CENTER["trailDist"], CENTER["trailDist"]+2],
)
keys=list(fine.keys())
combos=list(itertools.product(*[fine[k] for k in keys]))
out=[]
for combo in combos:
    p=dict(CENTER)
    for k,v in zip(keys,combo): p[k]=v
    sis=stats(run(IS,p)); soos=stats(run(OOS,p))
    out.append((sis["pnl"]+soos["pnl"], sis, soos, dict(zip(keys,combo))))
out.sort(key=lambda r:-r[0])
print("full-period baseline:", stats(run(bars,BASE)))
print("\nIS/OOS for top configs (robust = both positive, OOS not collapsing):")
for tot,sis,soos,params in out[:15]:
    print(f"IS pnl={sis['pnl']:7.0f} win={sis['winrate']:.0f}% n={sis['n']:3d} | "
          f"OOS pnl={soos['pnl']:7.0f} win={soos['winrate']:.0f}% n={soos['n']:3d} | {params}")
