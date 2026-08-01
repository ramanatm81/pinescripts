"""OOS: after K consecutive TRAIL-exit WINS, what does the NEXT trade do?
Total PnL split (win/loss). Prints K=2 and K=3 for comparison.

Trade tuple: (tradeDir, entryPrice, exitPrice, pnl, reason, entryWasDeep, dt)
  t[3]=pnl  t[4]=exit reason
'TRAIL win' = reason == 'TRAIL' AND pnl > 0.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BACKTEST_DATA"] = os.path.expanduser("~/Downloads/data.csv")
import backtest as bt
from collections import defaultdict

FUK = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

def is_trail_win(t):
    return t[4] == "TRAIL" and t[3] > 0

def analyze(trades, K, label):
    # trades[i] is a 'next' if the K trades immediately before it are ALL trail-wins
    nexts = []
    for i in range(K, len(trades)):
        if all(is_trail_win(trades[i-j]) for j in range(1, K+1)):
            nexts.append(trades[i])

    print(f"\n===== {label}: NEXT trade after {K} consecutive TRAIL wins =====")
    n = len(nexts)
    print(f"  triggers (with a following trade): {n}")
    if n == 0:
        print("  no occurrences")
        return

    wins   = [t for t in nexts if t[3] > 0]
    losses = [t for t in nexts if t[3] <= 0]
    wp, lp = sum(t[3] for t in wins), sum(t[3] for t in losses)
    tot = wp + lp
    print(f"    winners : {len(wins):>3}  pnl = {round(wp,1):>9}")
    print(f"    losers  : {len(losses):>3}  pnl = {round(lp,1):>9}")
    print(f"    -------------------------------------")
    print(f"    TOTAL   : {n:>3}  pnl = {round(tot,1):>9}   "
          f"win%={round(len(wins)/n*100,1)}  avg={round(tot/n,2)}")

    br = defaultdict(lambda: [0, 0.0])
    for t in nexts:
        br[t[4]][0] += 1; br[t[4]][1] += t[3]
    print(f"    exit-reason split of the NEXT trades:")
    for r,(c,p) in sorted(br.items(), key=lambda kv:-kv[1][1]):
        print(f"      {r:<8} n={c:>3}  pnl={round(p,1):>9}")

    aw = sum(1 for t in trades if t[3] > 0)
    print(f"    (baseline all-trades win%={round(aw/len(trades)*100,1)}, "
          f"avg={round(sum(t[3] for t in trades)/len(trades),2)})")

bars = bt.load()
print(f"OOS: {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}")

for label, cfg in [("toggles OFF (Fukuoka-shipped)", dict(FUK, blockLunch=False, blockAsia=False))]:
    tr = bt.run(bars, cfg)
    print(f"\n### {label}  (book: {len(tr)} trades)")
    analyze(tr, 2, label)
    analyze(tr, 3, label)
    analyze(tr, 4, label)
