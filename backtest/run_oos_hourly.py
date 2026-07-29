"""Where do the LOSERS actually sit on OOS? Break the toggles-OFF trade set down
by CT hour, and mark which hours the lunch/asia toggles cover. Answers: do the
toggles remove the loss-making hours, or do the big losers live OUTSIDE the
toggle windows (i.e. toggles don't help the wrong run)?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BACKTEST_DATA"] = os.path.expanduser("~/Downloads/data.csv")
import backtest as bt
from datetime import timezone, timedelta
from collections import defaultdict

FUK = dict(slopeEntry=2.5, slPts=50.0, enableSmaSL=True, smaPeriod=9,
           slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
           trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
           tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
           cooldownBars=10, cooldownBarsRTH=10, deepSlope=3.0)

def ctmin(dt):
    ct = dt.astimezone(timezone(timedelta(hours=-5)))
    return ct.hour*60 + ct.minute

bars = bt.load()
tr = bt.run(bars, dict(FUK, blockLunch=False, blockAsia=False))  # toggles OFF
print(f"OOS toggles-OFF: {len(tr)} trades, net {round(sum(t[3] for t in tr),1)}\n")

# bucket by CT hour
by_hr = defaultdict(list)
for t in tr:
    by_hr[ctmin(t[6])//60].append(t[3])

def lbl(h):
    tags = []
    m = h*60
    if 600 <= m < 780: tags.append("LUNCH-blk")
    if m >= 1320 or m < 300: tags.append("ASIA-blk")
    if 120 <= m < 150: tags.append("LNopen-blk")
    if 450 <= m < 540: tags.append("preNY-blk")
    if 1020 <= m < 1050: tags.append("ETHopen-blk")
    return " ".join(tags)

print(f"{'CT hr':>5} {'n':>4} {'net':>9} {'win%':>6} {'worst':>8}   blocked-by")
tot_blocked_net = 0; tot_open_net = 0
for h in sorted(by_hr):
    v = by_hr[h]
    n = len(v); net = round(sum(v),1); win = round(sum(1 for x in v if x>0)/n*100,0)
    worst = round(min(v),1)
    tags = lbl(h)
    blocked = ("LUNCH-blk" in tags) or ("ASIA-blk" in tags)
    if blocked: tot_blocked_net += net
    else: tot_open_net += net
    star = " <== toggles remove" if blocked else ""
    print(f"{h:>5} {n:>4} {net:>9} {win:>5}% {worst:>8}   {tags}{star}")

print(f"\nnet in NEW-toggle windows (lunch+asia, removed): {round(tot_blocked_net,1)}")
print(f"net OUTSIDE new-toggle windows (kept):          {round(tot_open_net,1)}")

# biggest single losers and where they sit
losers = sorted(tr, key=lambda t: t[3])[:10]
print("\n10 worst single trades (toggles-OFF) and their CT hour + block status:")
for t in losers:
    m = ctmin(t[6]); h = m//60
    inblk = (600<=m<780) or (m>=1320 or m<300)
    print(f"  {str(t[6])[:16]}  CTmin={m:>4} (hr{h:>2})  pnl={t[3]:>7}  {'REMOVED by toggle' if inblk else 'NOT removed'}")
