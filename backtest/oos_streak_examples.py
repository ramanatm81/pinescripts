"""List every occurrence of 3 consecutive TRAIL wins on OOS, showing the 3
winners (time/dir/pnl) and the NEXT trade (time/dir/pnl/reason).

Trade tuple: (tradeDir, entryPrice, exitPrice, pnl, reason, entryWasDeep, dt)
Times shown in London (Europe/London) to match the user's chart clock.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BACKTEST_DATA"] = os.path.expanduser("~/Downloads/data.csv")
import backtest as bt
from datetime import timezone, timedelta

FUK = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

def is_trail_win(t):
    return t[4] == "TRAIL" and t[3] > 0

def ldn(dt):
    # dt is tz-aware (parsed from ISO). Show London wall clock.
    # London in July = BST = UTC+1
    l = dt.astimezone(timezone(timedelta(hours=1)))
    return l.strftime("%m-%d %H:%M")

def d(t):
    return "L" if t[0] == 1 else "S"

bars = bt.load()
tr = bt.run(bars, dict(FUK, blockLunch=False, blockAsia=False))
print(f"OOS book: {len(tr)} trades\n")

K = 3
count = 0
for i in range(K, len(tr)):
    if all(is_trail_win(tr[i-j]) for j in range(1, K+1)):
        count += 1
        w = [tr[i-3], tr[i-2], tr[i-1]]
        nx = tr[i]
        wtxt = "  ".join(f"{ldn(t[6])} {d(t)} +{t[3]:.0f}" for t in w)
        res = "WIN " if nx[3] > 0 else "LOSS"
        print(f"#{count:>2} | 3 wins: {wtxt}")
        print(f"     -> NEXT: {ldn(nx[6])} {d(nx)} {nx[3]:+.1f} [{nx[4]}]  {res}")
print(f"\ntotal occurrences: {count}")
wins = 0; losses = 0
for i in range(K, len(tr)):
    if all(is_trail_win(tr[i-j]) for j in range(1, K+1)):
        if tr[i][3] > 0: wins += 1
        else: losses += 1
print(f"next-trade: {wins} win / {losses} loss")
