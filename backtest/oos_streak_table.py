"""Table: every occurrence of 3 consecutive TRAIL wins on OOS -> the next trade.
One row per occurrence. Times in London (chart clock). Dir L=long S=short."""
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

def is_trail_win(t): return t[4] == "TRAIL" and t[3] > 0
def ldn(dt): return dt.astimezone(timezone(timedelta(hours=1))).strftime("%m-%d %H:%M")
def dr(t):  return "L" if t[0] == 1 else "S"

bars = bt.load()
tr = bt.run(bars, dict(FUK, blockLunch=False, blockAsia=False))

hdr = (f"{'#':>3} | {'win1':>12} {'':>2}{'pnl':>4} | {'win2':>12} {'':>2}{'pnl':>4} | "
       f"{'win3':>12} {'':>2}{'pnl':>4} || {'NEXT trade':>12} {'d':>1} {'pnl':>7} {'exit':>5} {'res':>4}")
print(hdr)
print("-" * len(hdr))

n = 0; wins = 0; losses = 0
for i in range(3, len(tr)):
    if all(is_trail_win(tr[i-j]) for j in (1,2,3)):
        n += 1
        a,b,c = tr[i-3], tr[i-2], tr[i-1]
        x = tr[i]
        res = "WIN" if x[3] > 0 else "LOSS"
        if x[3] > 0: wins += 1
        else: losses += 1
        print(f"{n:>3} | {ldn(a[6]):>12} {dr(a):>2}{a[3]:>4.0f} | "
              f"{ldn(b[6]):>12} {dr(b):>2}{b[3]:>4.0f} | "
              f"{ldn(c[6]):>12} {dr(c):>2}{c[3]:>4.0f} || "
              f"{ldn(x[6]):>12} {dr(x):>1} {x[3]:>+7.1f} {x[4]:>5} {res:>4}")

print("-" * len(hdr))
tot = sum(tr[i][3] for i in range(3,len(tr))
          if all(is_trail_win(tr[i-j]) for j in (1,2,3)))
print(f"occurrences={n}   next-trade: {wins} WIN / {losses} LOSS   net={round(tot,1)}")
