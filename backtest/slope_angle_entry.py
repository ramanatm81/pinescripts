import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10, enableThrdReversal=False,
            angleEntry=True, angleAtrLen=14,
            enableSmaSL=False, slPts=100.0)

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except: continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars

def summ(trs, slip, years):
    p=[t[3]-slip for t in trs]; n=len(p)
    if n==0: return 0,0,0,0,[0]*len(years),0
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    yl=[]; pos=0
    for y in years:
        yy=round(sum(t[3]-slip for t in trs if t[6].year==y))
        if yy>0: pos+=1
        yl.append(yy)
    return round(sum(p)), n, round(gp/gl,2) if gl>0 else 999, round(100*w/n,1), yl, pos

if __name__=="__main__":
    print("loading...")
    bars=load()
    years=[2021,2022,2023,2024,2025,2026]
    print("bars %d"%len(bars))
    print()
    print("ANGLE ENTRY (ATR14-normalized), fixed SL100, trail 30/8-10, all base blocks on. 5yr")
    print("baseline slope entry (2.5) for reference:")
    for slip in (0.0,1.0):
        trs=bt.run(bars, dict(BASE, angleEntry=False, enableSmaSL=True, slAboveSma=50.0, slBelowSma=30.0))
        pnl,n,pf,win,yl,pos=summ(trs,slip,years)
        print("  slope2.5 SMA-SL slip%.0f | pnl %6d n %5d pf %4.2f win %4.1f | %d/6 | %s"%(slip,pnl,n,pf,win,pos,yl))
    print()
    print("angle threshold sweep (fixed SL100):")
    print("  %6s | %7s %7s | %5s %5s %5s | +yr | per-year(1pt)"%("angle","pnl0","pnl1","n","pf","win"))
    for ang in (7.0, 8.0, 9.5, 11.0, 13.0):
        trs=bt.run(bars, dict(BASE, angleThresh=ang))
        pnl0,n,pf,win,yl0,pos0=summ(trs,0.0,years)
        pnl1,_,_,_,yl1,pos1=summ(trs,1.0,years)
        print("  %6.1f | %7d %7d | %5d %5.2f %5.1f | %d/6 | %s"%(ang,pnl0,pnl1,n,pf,win,pos1,yl1))
    print()
    print("SL sweep at angle 9.5:")
    print("  %5s | %7s %7s | %5s %5s %5s | +yr"%("SL","pnl0","pnl1","n","pf","win"))
    for sl in (50.0,70.0,100.0,150.0):
        trs=bt.run(bars, dict(BASE, angleThresh=9.5, slPts=sl))
        pnl0,n,pf,win,yl0,pos0=summ(trs,0.0,years)
        pnl1,_,_,_,yl1,pos1=summ(trs,1.0,years)
        print("  %5.0f | %7d %7d | %5d %5.2f %5.1f | %d/6"%(sl,pnl0,pnl1,n,pf,win,pos1))
