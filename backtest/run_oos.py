"""OOS run on ~/Downloads/data.csv. Compare toggles ON vs OFF, Fukuoka base.
Also prints how many trades fall in the lunch (600-780 CT) and asia windows so we
can SEE whether the toggles are even active on this slice."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BACKTEST_DATA"] = os.path.expanduser("~/Downloads/data.csv")
import backtest as bt
from datetime import timezone, timedelta

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

FUK = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

bars = bt.load()
print(f"OOS: {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}\n")

scenarios = {
    "toggles OFF (Fukuoka-as-shipped)":
        dict(FUK, blockLunch=False, blockAsia=False),
    "lunch ON only":
        dict(FUK, blockLunch=True, blockAsia=False),
    "asia ON only":
        dict(FUK, blockLunch=False, blockAsia=True),
    "BOTH toggles ON":
        dict(FUK, blockLunch=True, blockAsia=True),
    "ALL session blocks OFF":
        dict(FUK, blockLunch=False, blockAsia=False,
             blockLNOpen=False, blockPreNY=False, blockNYOpen=False),
}
for name, p in scenarios.items():
    tr = bt.run(bars, p)
    s = full_stats(tr)
    print(f"### {name}")
    print(f"    trades={s['n']}  net={s['pnl']}  win%={s['winrate']}  "
          f"PF={s['pf']}  (GP={s['gp']} / GL={s['gl']})  avg={s['avg']}")

# How many OFF-config trades sit inside each toggle window? (what the toggles remove)
tr = bt.run(bars, dict(FUK, blockLunch=False, blockAsia=False))
def ctmin(dt):
    ct = dt.astimezone(timezone(timedelta(hours=-5)))
    return ct.hour*60 + ct.minute
lunch = [t for t in tr if 600 <= ctmin(t[6]) < 780]
asia  = [t for t in tr if (ctmin(t[6]) >= 1320 or ctmin(t[6]) < 300)]
print("\n=== trades the toggles would REMOVE (from OFF config) ===")
ls, as_ = full_stats(lunch), full_stats(asia)
print(f"  lunch window (10:00-13:00 CT): n={ls['n']}  net={ls['pnl']}  win%={ls['winrate']}  PF={ls['pf']}")
print(f"  asia window  (22:00-05:00 CT): n={as_['n']}  net={as_['pnl']}  win%={as_['winrate']}  PF={as_['pf']}")
