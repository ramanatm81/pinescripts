#!/usr/bin/env python3
"""
Cut structural loser hours (CT) from the slope strategy and measure the REAL net
effect — not just the gross P&L of the removed hour, but the change in TOTAL net,
because blocking an entry also shifts cooldown/state and can drop the trail winner
that would have followed. Per the standing rule: also report removed-trade W/L so
we don't ship a filter that mostly cut future winners.

Baseline through 2026-06-23. Tests each candidate hour alone, then combos.
RAW + 1pt slippage.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def load_5yr():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return bars

def net(trades, slip=0.0):
    return sum(t[3]-slip for t in trades)

def wl(trades, slip=0.0):
    n=len(trades); w=sum(1 for t in trades if t[3]-slip>0)
    return n, (w/n*100 if n else 0)

if __name__=="__main__":
    print("loading 5yr data..."); bars=load_5yr()
    print(f"loaded {len(bars):,} bars, {bars[0][0].date()} -> {bars[-1][0].date()}\n")

    base_tr = bt.run(bars, BASE)
    base_ids = {(t[6], t[0], t[1]) for t in base_tr}   # identity: (dt, dir, entry)

    # candidate loser hours (CT) from the profiling: 15 (worst, 44% win), 4, 1, 2, 19
    candidates = {
        "cut 15":       [15],
        "cut 04":       [4],
        "cut 01":       [1],
        "cut 02":       [2],
        "cut 19":       [19],
        "cut 15+04":    [15,4],
        "cut 15+04+01+02": [15,4,1,2],
        "cut 15+04+01+02+19": [15,4,1,2,19],
    }

    for slip in (0.0, 1.0):
        b = net(base_tr, slip)
        print(f"{'='*84}\nCUT LOSER HOURS   (slippage={slip})   baseline net = {b:.0f} pts, {len(base_tr)} tr\n{'='*84}")
        print(f"{'variant':<22}{'net':>10}{'delta':>10}{'trades':>8}"
              f"{'removed':>9}{'rem W/L%':>10}{'kept-win%':>10}")
        print("-"*84)
        for name, hrs in candidates.items():
            tr = bt.run(bars, dict(BASE, blockHoursCT=set(hrs)))
            new_ids = {(t[6],t[0],t[1]) for t in tr}
            removed = [t for t in base_tr if (t[6],t[0],t[1]) not in new_ids]
            rn, rwl = wl(removed, slip)
            n2, w2 = wl(tr, slip)
            nn = net(tr, slip); d = nn - b
            flag = " <-- WORSE" if d < 0 else ""
            print(f"{name:<22}{nn:>10.0f}{d:>+10.0f}{n2:>8}{rn:>9}{rwl:>9.0f}%{w2:>9.1f}%{flag}")
        print()
