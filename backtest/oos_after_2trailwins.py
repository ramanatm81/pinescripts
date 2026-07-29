"""OOS: after TWO consecutive TRAIL-exit winning trades, what does the NEXT
trade do? Total PnL split (win/loss) of those 'next' trades.

Trade tuple: (tradeDir, entryPrice, exitPrice, pnl, reason, entryWasDeep, dt)
  t[3]=pnl  t[4]=exit reason  t[6]=entry timestamp
'TRAIL victory' = reason == 'TRAIL' AND pnl > 0.

Config = Fukuoka base. Runs BOTH toggle states so we can see both, since the
user's current OOS interest has been the toggles-ON book.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BACKTEST_DATA"] = os.path.expanduser("~/Downloads/data.csv")
import backtest as bt

FUK = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

def is_trail_win(t):
    return t[4] == "TRAIL" and t[3] > 0

def analyze(trades, label):
    # walk the sequence; when trades[i-1] and trades[i-2] are both trail-wins,
    # trades[i] is a 'next after 2 consecutive trail wins'
    nexts = []
    for i in range(2, len(trades)):
        if is_trail_win(trades[i-1]) and is_trail_win(trades[i-2]):
            nexts.append(trades[i])

    n = len(nexts)
    print(f"\n===== {label} =====")
    print(f"total trades in book: {len(trades)}")
    print(f"triggers (2 consecutive TRAIL wins, with a following trade): {n}")
    if n == 0:
        print("  no occurrences")
        return

    wins   = [t for t in nexts if t[3] > 0]
    losses = [t for t in nexts if t[3] <= 0]
    win_pnl  = sum(t[3] for t in wins)
    loss_pnl = sum(t[3] for t in losses)
    total    = win_pnl + loss_pnl

    print(f"  NEXT-trade outcomes:")
    print(f"    winners : {len(wins):>3}  pnl = {round(win_pnl,1):>9}")
    print(f"    losers  : {len(losses):>3}  pnl = {round(loss_pnl,1):>9}")
    print(f"    -------------------------------------")
    print(f"    TOTAL   : {n:>3}  pnl = {round(total,1):>9}   "
          f"win%={round(len(wins)/n*100,1)}  avg={round(total/n,2)}")

    # exit-reason breakdown of the next trades
    from collections import Counter, defaultdict
    by_reason = defaultdict(lambda: [0,0.0])
    for t in nexts:
        by_reason[t[4]][0] += 1
        by_reason[t[4]][1] += t[3]
    print(f"  NEXT-trade exit-reason split:")
    for r,(c,p) in sorted(by_reason.items(), key=lambda kv:-kv[1][1]):
        print(f"    {r:<8} n={c:>3}  pnl={round(p,1):>9}")

    # baseline: all-trades win% for comparison
    aw = sum(1 for t in trades if t[3] > 0)
    print(f"  (baseline all-trades win% = {round(aw/len(trades)*100,1)}, "
          f"avg = {round(sum(t[3] for t in trades)/len(trades),2)})")

bars = bt.load()
print(f"OOS: {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}")

analyze(bt.run(bars, dict(FUK, blockLunch=True,  blockAsia=True)),  "BOTH toggles ON")
analyze(bt.run(bars, dict(FUK, blockLunch=False, blockAsia=False)), "toggles OFF (Fukuoka-shipped)")
