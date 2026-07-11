#!/usr/bin/env python3
"""
Slope strategy tuning (per user 2026-07-11): cut trade count + cut the -50 SL losses.
  1) Disable THRD reversal entries (enableThrdReversal=False) — THRD still EXITS a losing
     trade, just no reversed re-entry. Cuts trade count.
  2) Tighten the above-SMA SL (slAboveSma, the -50 loss) toward 30 (=slBelowSma).

All runs at 1pt/trade slippage (honest). Baseline = Fukuoka.
Compare: baseline / noTHRD / noTHRD+SL40 / noTHRD+SL30. Per-year + trade count + SL-loss total.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
import os
SLIP=float(os.environ.get("SLIP","1.0"))
BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def load():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return bars

def analyze(name, bars, params, years):
    trs=bt.run(bars, params)
    # trade tuple: (dir, entry, exit, pnl, reason, deep, dt)
    p=[t[3]-SLIP for t in trs]; n=len(p)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    pnl=round(sum(p)); pf=round(gp/gl,2) if gl>0 else 999; win=round(100*w/n,1) if n else 0
    # SL-loss stats
    sl=[t for t in trs if t[4]=='SL']
    sl_pnl=round(sum(t[3] for t in sl))
    sl50=sum(1 for t in sl if round(t[3])==-50)
    # per year
    yline=[]; pos=0
    for y in years:
        yp=[t[3]-SLIP for t in trs if t[6].year==y]
        yy=round(sum(yp))
        if yy>0: pos+=1
        yline.append(yy)
    thrd_n=sum(1 for t in trs if t[4]=='THRD')
    print(f"{name:22} | pnl {pnl:>7} n {n:>5} pf {pf:>4} win {win:>5} | SLloss {sl_pnl:>7} (#-50: {sl50}) THRDx {thrd_n} | {pos}/6 | {yline}")

if __name__=="__main__":
    print("loading…"); bars=load()
    years=[2021,2022,2023,2024,2025,2026]
    print(f"bars {len(bars):,}  (1pt slip)\n")
    print(f"{'config':22} | {'pnl':>11} {'n':>7} {'pf':>7} {'win':>9} | {'SL info':>26} | +yr | per-year")
    analyze("baseline (Fukuoka)", bars, dict(BASE), years)
    analyze("noTHRD entries",     bars, dict(BASE, enableThrdReversal=False), years)
    analyze("noTHRD + SLabove40", bars, dict(BASE, enableThrdReversal=False, slAboveSma=40.0), years)
    analyze("noTHRD + SLabove30", bars, dict(BASE, enableThrdReversal=False, slAboveSma=30.0), years)
    # also SL tighten alone (keep THRD) for comparison
    analyze("SLabove30 (keepTHRD)",bars, dict(BASE, slAboveSma=30.0), years)
