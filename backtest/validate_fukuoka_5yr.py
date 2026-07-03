#!/usr/bin/env python3
"""Validate the Fukuoka slope-strategy optimization (tuned on 18 days) against
the full 5 years. Writes results to fukuoka_5yr_results.txt."""
import csv
from datetime import datetime, timezone, timedelta
import backtest as B

def load5():
    bars=[]
    with open('/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv') as f:
        for row in csv.DictReader(f):
            try: o=float(row['open']);h=float(row['high']);l=float(row['low']);c=float(row['close'])
            except: continue
            dt=datetime.fromisoformat(row['time']).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return bars

def cfg(**o):
    base=dict(slopeEntry=2.5,slAboveSma=50.0,slBelowSma=30.0,tpPts=50.0,tpMult=3.0,
              trailTrigger=30.0,trailDist=8.0,trailDistStrong=10.0,tExpBars=20,
              tExpHardBars=20,tExpHardSlope=1.0)
    base.update(o); return base

def main():
    bars=load5()
    # pre-split by year once (avoid re-filtering 1.77M rows per config)
    byyr={yr:[b for b in bars if b[0].year==yr] for yr in range(2021,2027)}
    out=[]
    def line(s): out.append(s); print(s, flush=True)
    def evalc(name,c):
        full=B.stats(B.run(bars,c))
        ys=[B.stats(B.run(byyr[yr],c))['pnl'] for yr in range(2021,2027)]
        pw=sum(1 for y in ys if y>0)
        line(f"{name:22s} full={full['pnl']:8.0f} win{full['winrate']:.0f}% n{full['n']} | {pw}/6 yrs | {[round(y) for y in ys]}")

    line("=== Fukuoka slope defaults validated on 5yr (was tuned on 18 days) ===\n")
    line("-- slopeEntry (Fukuoka=2.5, pre-Fukuoka=1.7) --")
    for se in [1.7,2.0,2.5,3.0]: evalc(f"slopeEntry={se}", cfg(slopeEntry=se))
    line("\n-- trailDist (Fukuoka=8, pre=10) --")
    for td in [8,10,12]: evalc(f"trailDist={td}", cfg(trailDist=td))
    line("\n-- tpPts (Fukuoka=50, pre=40) --")
    for tp in [40,50,60]: evalc(f"tpPts={tp}", cfg(tpPts=tp))
    line("\n-- tExpBars (Fukuoka=20, pre=30) --")
    for te in [20,30]: evalc(f"tExpBars={te}", cfg(tExpBars=te))
    line("\n-- pre-Fukuoka vs Fukuoka head-to-head --")
    evalc("PRE-Fukuoka(1.7)", cfg(slopeEntry=1.7,trailDist=10,tpPts=40,tExpBars=30))
    evalc("FUKUOKA(2.5)", cfg())

    with open("fukuoka_5yr_results.txt","w") as f: f.write("\n".join(out)+"\n")
    print("\nwrote fukuoka_5yr_results.txt")

if __name__=="__main__": main()
