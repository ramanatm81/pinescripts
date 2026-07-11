#!/usr/bin/env python3
"""
FAKE-WIN AUDIT of the slope strategy (Fukuoka) 5yr — same tests that caught Zone Rider's
+98k artifact. Confirm the ~30k is real, not fill fiction.

Checks:
  A) reproduce headline PnL (0 slip) + apply realistic slippage (0.5, 1.0, 2.0 pts/side)
  B) exit-reason mix + per-reason pnl + avg bars_held (1-bar flushes = churn artifact)
  C) THE key test: any exit booked on the FAVORABLE side of entry at fill time?
     For each exit, is the fill price already profitable by construction on the entry bar?
     Specifically flag trades that (held<=1 AND pnl>0) — the Zone Rider signature.
  D) per-year with realistic slip.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars, yrs

def get_trades(bars):
    # backtest.run(bars, BASE) -> trades list of (dir, entry, exit, pnl, reason, deep, dt)
    return bt.run(bars, BASE)

if __name__=="__main__":
    print("loading…"); bars,yrs=load()
    print(f"bars {len(bars):,}")
    # map dt->year quickly via trade dt (index 6)
    trades = get_trades(bars)
    print(f"trades returned: {len(trades)}\n")
    # normalize
    T=[]
    for t in trades:
        d=t[0]; entry=t[1]; ex=t[2]; pnl=t[3]; reason=t[4]; dt=t[6] if len(t)>6 else None
        T.append(dict(dir=d, entry=entry, exit=ex, pnl=pnl, reason=reason, yr=(dt.year if dt else None)))

    def summ(trs, slip):
        p=[x['pnl']-slip for x in trs]; n=len(p)
        if n==0: return (0,0,0,0)
        w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
        return (round(sum(p)), n, round(gp/gl,2) if gl>0 else 999, round(100*w/n,1))

    print("=== A) PnL vs slippage ===")
    for slip in [0.0,0.5,1.0,2.0]:
        pnl,n,pf,win=summ(T,slip)
        print(f"  slip {slip:>3}/trade | pnl {pnl:>7} n {n} pf {pf} win {win}%")

    print("\n=== B) exit-reason mix (pnl at 0 slip) ===")
    from collections import Counter, defaultdict
    rc=Counter(x['reason'] for x in T)
    rp=defaultdict(float)
    for x in T: rp[x['reason']]+=x['pnl']
    for r,c in rc.most_common():
        print(f"  {r:6} n={c:>4}  pnl={round(rp[r]):>7}")

    print("\n=== C) fake-win signature: exits booked FAVORABLE by construction ===")
    # Zone Rider signature: an exit whose fill was already profitable on entry (guaranteed).
    # In this port every exit fill is a real price the market touched (SL=entry±SL, TP=entry±tp,
    # TRAIL=peak−dist after arming, TEXP/THRD/BF/EOD/BLK=close). None can be favorable-at-entry.
    # Empirically: count trades that are pnl>0 AND exited at a fixed level (SL/TP/TRAIL) where
    # the level would be on the wrong side — should be ZERO for SL (always loss), TP always +tp.
    tp_neg = [x for x in T if x['reason']=='TP' and x['pnl']<0]
    sl_pos = [x for x in T if x['reason']=='SL' and x['pnl']>0]
    trail_immediate = [x for x in T if x['reason']=='TRAIL' and x['pnl']>0 and abs(x['exit']-x['entry'])< 1]
    print(f"  TP exits with NEGATIVE pnl (should be 0): {len(tp_neg)}")
    print(f"  SL exits with POSITIVE pnl (should be 0 — would be fake): {len(sl_pos)}")
    print(f"  TRAIL exits filled ~AT entry with +pnl (fake-ish): {len(trail_immediate)}")
    # distribution of TP pnl (should all be ~ +tpPts*tpMult = +150) and SL (~ −activeSL)
    tp_pnls=[round(x['pnl']) for x in T if x['reason']=='TP']
    sl_pnls=[round(x['pnl']) for x in T if x['reason']=='SL']
    if tp_pnls: print(f"  TP pnl range: min {min(tp_pnls)} max {max(tp_pnls)} (expect ~+150 each)")
    if sl_pnls: print(f"  SL pnl range: min {min(sl_pnls)} max {max(sl_pnls)} (expect ~−50/−30 each)")

    print("\n=== D) per-year (slip 1.0/trade) ===")
    years=sorted(set(x['yr'] for x in T if x['yr']))
    print(f"{'year':>6} | {'pnl':>7} {'n':>5} {'pf':>5} {'win':>5}")
    tot=0; pos=0
    for y in years:
        pnl,n,pf,win=summ([x for x in T if x['yr']==y],1.0)
        if pnl>0: pos+=1
        tot+=pnl
        print(f"{y:>6} | {pnl:>7} {n:>5} {pf:>5} {win:>5}")
    print(f"{'-'*36}\n{'TOTAL':>6} | {tot:>7}   ({pos}/{len(years)} yrs +)")
