#!/usr/bin/env python3
"""Detail for specific LDN hours: gross win/loss + net, per LDN clock hour."""
import sys, os, importlib
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

WANT = {12, 13, 14}  # LDN hours to detail

def run_file(path, name):
    os.environ["BACKTEST_DATA"] = path
    importlib.reload(bt)
    bars = bt.load(); trades = bt.run(bars, BASE)
    print(f"\n######## {name}  ({len(trades)} trades) ########")
    for slip in (0.0, 1.0):
        by = defaultdict(lambda: {"n":0,"pnl":0.0,"w":0,"l":0,"gw":0.0,"gl":0.0})
        for (d,en,ex,pnl,reason,deep,dt) in trades:
            ldn = (dt.hour + 6) % 24
            if ldn not in WANT: continue
            p = pnl - slip
            b = by[ldn]; b["n"]+=1; b["pnl"]+=p
            if p>0: b["w"]+=1; b["gw"]+=p
            else: b["l"]+=1; b["gl"]+=p
        print(f"\n  {name} — slip {slip}")
        print(f"  {'LDN hr':<8}{'trades':>7}{'win%':>7}{'WIN pnl':>10}{'LOSS pnl':>10}{'NET':>9}{'PF':>6}")
        for ldn in (12,13,14):
            b = by.get(ldn)
            if not b:
                print(f"  {f'{ldn}:00':<8}{0:>7}{'—':>7}{'—':>10}{'—':>10}{'—':>9}{'—':>6}  (no trades)")
                continue
            wr=b["w"]/b["n"]*100 if b["n"] else 0
            pf=b["gw"]/abs(b["gl"]) if b["gl"] else 99.9
            print(f"  {f'{ldn}:00':<8}{b['n']:>7}{wr:>6.1f}%{b['gw']:>10.0f}{b['gl']:>10.0f}{b['pnl']:>9.0f}{pf:>6.2f}")

if __name__=="__main__":
    run_file("/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv","5-YEAR")
    run_file("/Users/maheshk81/Downloads/data.csv","OOS")
