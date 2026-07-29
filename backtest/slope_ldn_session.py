#!/usr/bin/env python3
"""
Win/loss stats bucketed by LONDON session (chart time the user reads).
LDN hour = (CT hour + 6) % 24  [CDT UTC-5 -> BST UTC+1].

LDN session boundaries (London clock):
  ASIA    23:00-06:59   (overnight / Asia)
  LDN_AM  07:00-11:59   (London morning)
  LDN/US  12:00-14:59   (London afternoon + US pre-open)
  US_OPEN 15:00-16:59   (US cash open — the known engine)
  US_PM   17:00-21:59   (US afternoon)
  LATE    22:00-22:59   (US close edge)
"""
import sys, os, importlib
from collections import defaultdict
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import backtest as bt

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def ldn_session(ldn_h):
    if ldn_h >= 23 or ldn_h <= 6:  return "ASIA    23-07"
    if 7  <= ldn_h <= 11:          return "LDN_AM  07-12"
    if 12 <= ldn_h <= 14:          return "LDN/US  12-15"
    if 15 <= ldn_h <= 16:          return "US_OPEN 15-17"
    if 17 <= ldn_h <= 21:          return "US_PM   17-22"
    return "LATE    22-23"

ORDER = ["ASIA    23-07","LDN_AM  07-12","LDN/US  12-15","US_OPEN 15-17","US_PM   17-22","LATE    22-23"]

def bucket(trades, slip):
    by = defaultdict(lambda: {"n":0,"pnl":0.0,"w":0,"l":0,"gw":0.0,"gl":0.0,"worst":0.0})
    for (d,en,ex,pnl,reason,deep,dt) in trades:
        pnl -= slip
        s = ldn_session((dt.hour+6)%24)
        b = by[s]; b["n"]+=1; b["pnl"]+=pnl
        if pnl>0: b["w"]+=1; b["gw"]+=pnl
        else: b["l"]+=1; b["gl"]+=pnl; b["worst"]=min(b["worst"],pnl)
    return by

def report(trades, slip, label):
    by = bucket(trades, slip)
    tp = sum(b["pnl"] for b in by.values()); tn=sum(b["n"] for b in by.values())
    print(f"\n{'='*90}\n{label}  (slip {slip})\n{'='*90}")
    print(f"{'LDN session':<15}{'trades':>7}{'win%':>7}{'WIN pnl':>10}{'LOSS pnl':>10}"
          f"{'NET':>9}{'PF':>6}{'avgW':>7}{'avgL':>7}{'worst':>7}")
    print("-"*90)
    tgw=sum(b["gw"] for b in by.values()); tgl=sum(b["gl"] for b in by.values())
    for s in ORDER:
        if s not in by: continue
        b=by[s]
        wr=b["w"]/b["n"]*100 if b["n"] else 0
        aw=b["gw"]/b["w"] if b["w"] else 0
        al=b["gl"]/b["l"] if b["l"] else 0
        pf=b["gw"]/abs(b["gl"]) if b["gl"] else 99.9
        print(f"{s:<15}{b['n']:>7}{wr:>6.1f}%{b['gw']:>10.0f}{b['gl']:>10.0f}"
              f"{b['pnl']:>9.0f}{pf:>6.2f}{aw:>7.1f}{al:>7.1f}{b['worst']:>7.0f}")
    print("-"*90)
    print(f"{'TOTAL':<15}{tn:>7}{'':>7}{tgw:>10.0f}{tgl:>10.0f}{tp:>9.0f}"
          f"{tgw/abs(tgl) if tgl else 0:>6.2f}")

def run_file(path, name):
    os.environ["BACKTEST_DATA"]=path
    importlib.reload(bt)
    bars=bt.load(); trades=bt.run(bars,BASE)
    print(f"\n######## {name}  ({len(trades)} trades) ########")
    report(trades,0.0,f"{name} — RAW")
    report(trades,1.0,f"{name} — 1pt slip")

if __name__=="__main__":
    run_file("/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv","5-YEAR")
    run_file("/Users/maheshk81/Downloads/data.csv","OOS")
