import csv, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

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

def run(bars, p):
    lookback   = p.get("lookback",10)
    dojiPct    = p.get("dojiPct",10.0)
    armLevel   = p.get("armLevel",-11.0)
    recovLevel = p.get("recovLevel",-5.0)
    trailTrig  = p.get("trailTrigger",40.0)
    trailDist  = p.get("trailDist",25.0)
    slip       = p.get("slip",0.0)

    slopeBuf=[]; legSlope=None
    armed=False
    inTrade=False; entryPrice=None; bestPrice=None; trailStop=None; entryBar=None
    entryDt=None
    trades=[]

    for bi,(dt,o,h,l,c,ctm) in enumerate(bars):
        eodClose = 900 <= ctm < 960
        rng=h-l
        bodyPct=(abs(c-o)/rng*100.0) if rng>0 else 0.0
        isDoji=bodyPct < dojiPct

        legSlope=None
        if not eodClose and not isDoji:
            slopeBuf.append(c)
            if len(slopeBuf)>lookback: slopeBuf.pop(0)
        if len(slopeBuf)==lookback:
            n=lookback; sx=sy=sxy=sx2=0.0
            for i in range(n):
                x=float(i); y=slopeBuf[i]
                sx+=x; sy+=y; sxy+=x*y; sx2+=x*x
            den=n*sx2-sx*sx
            legSlope=round((n*sxy-sx*sy)/den,2) if den!=0 else 0.0

        if inTrade:
            bestPrice=max(bestPrice,h)
            if bestPrice-entryPrice >= trailTrig:
                ts=bestPrice-trailDist
                trailStop=ts if trailStop is None else max(trailStop,ts)
            exitReason=None; exitPrice=None
            if trailStop is not None and l<=trailStop:
                exitReason="TRAIL"; exitPrice=trailStop
            elif legSlope is not None and legSlope<=armLevel:
                exitReason="SLOPE11"; exitPrice=c
            if exitReason:
                pnl=(exitPrice-entryPrice)-slip
                trades.append(dict(entryDt=entryDt, exitDt=dt, entry=entryPrice, exit=exitPrice,
                                   pts=pnl, reason=exitReason, bars=bi-entryBar,
                                   mfe=bestPrice-entryPrice))
                inTrade=False; entryPrice=None; bestPrice=None; trailStop=None
                armed=False

        if not inTrade and legSlope is not None:
            if legSlope<=armLevel:
                armed=True
            if armed and legSlope>=recovLevel and not eodClose:
                inTrade=True; entryPrice=c; bestPrice=c; trailStop=None
                entryBar=bi; entryDt=dt; armed=False

    return trades

def summarize(trades, label):
    n=len(trades)
    if n==0:
        print(label, "0 trades"); return
    net=sum(t["pts"] for t in trades)
    wins=[t for t in trades if t["pts"]>0]; loss=[t for t in trades if t["pts"]<=0]
    gw=sum(t["pts"] for t in wins); gl=sum(t["pts"] for t in loss)
    pf=gw/abs(gl) if gl else float("inf")
    avgbars=sum(t["bars"] for t in trades)/n
    byreason=defaultdict(lambda:[0,0.0])
    for t in trades: byreason[t["reason"]][0]+=1; byreason[t["reason"]][1]+=t["pts"]
    print("="*74)
    print(label)
    print("="*74)
    print(f"trades {n}  net {net:.0f} pts  (${net*2:.0f} 1MNQ)  PF {pf:.2f}  win {len(wins)/n*100:.0f}%")
    print(f"avg win {gw/len(wins) if wins else 0:.1f}  avg loss {gl/len(loss) if loss else 0:.1f}"
          f"  avg bars held {avgbars:.0f}  ({avgbars/60:.1f}h at 1m)")
    print(f"biggest win {max(t['pts'] for t in trades):.0f}  biggest loss {min(t['pts'] for t in trades):.0f}"
          f"  max MFE {max(t['mfe'] for t in trades):.0f}")
    for r in sorted(byreason, key=lambda k:-byreason[k][1]):
        cnt,pp=byreason[r]
        print(f"   {r:<8} {cnt:>5} tr  {pp:>8.0f} pts")

if __name__=="__main__":
    print("loading 5yr..."); bars=load_5yr()
    print(f"{len(bars):,} bars {bars[0][0].date()} -> {bars[-1][0].date()}\n")
    base=dict(armLevel=-11.0, recovLevel=-5.0, trailTrigger=40.0, trailDist=25.0)
    tr=run(bars, base)
    summarize(tr, "SLOPE RECOVERY LONG  arm-11 recov-5 trailTrig40 trailDist25  RAW")
    tr1=run(bars, dict(base, slip=1.0))
    summarize(tr1, "same  1pt slippage")

    yr=defaultdict(lambda:[0,0.0])
    for t in tr: yr[t["entryDt"].year][0]+=1; yr[t["entryDt"].year][1]+=t["pts"]
    print("\nBY YEAR (raw):")
    for y in sorted(yr): print(f"  {y}  {yr[y][0]:>4} tr  {yr[y][1]:>8.0f} pts")
