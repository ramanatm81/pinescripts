import csv, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

CSV5 = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
RECENT = "/Users/maheshk81/Downloads/data.csv"

def load(path, tz):
    bars=[]
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            t=r.get("time")
            if not t: continue
            try: o=float(r["open"]);h=float(r["high"]);l=float(r["low"]);c=float(r["close"])
            except: continue
            dt=datetime.fromisoformat(t).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return bars

def atr(H,L,C,i,n):
    s=0.0
    for k in range(i-n+1,i+1): s+=max(H[k]-L[k],abs(H[k]-C[k-1]),abs(L[k]-C[k-1]))
    return s/n

def run(bars, p):
    H=[b[2] for b in bars]; L=[b[3] for b in bars]; C=[b[4] for b in bars]; O=[b[1] for b in bars]; M=[b[5] for b in bars]
    vBars=p["vBars"]; tailFrac=p["tailFrac"]; legAtrMult=p["legAtrMult"]; legAtrLen=p["legAtrLen"]
    legMinAbs=p["legMinAbs"]; rearmBars=p["rearmBars"]; numHighs=p["numHighs"]; maxSpan=p["maxSpanBars"]
    slPts=p["slPts"]; trailTrig=p["trailTrig"]; trailDist=p["trailDist"]; slip=p["slip"]
    obStart=p["openStartCT"]; obEnd=p["openEndCT"]; blockOpens=p["blockOpens"]

    prevRawUp=False; upCool=0
    upCount=0; lastUpHi=None; upFirstBar=0
    signals=[]
    for i in range(vBars,len(bars)):
        upCool=max(0,upCool-1)
        wh=max(H[i-vBars+1:i+1]); hiA=i
        for k in range(i-vBars+1,i+1):
            if H[k]>=wh: hiA=k
        hiIdx=hiA-(i-vBars+1)
        fc=C[i-vBars+1]; a=atr(H,L,C,i,legAtrLen); lr=max(legAtrMult*a,legMinAbs)
        riseInto=wh-fc
        tailStart=(vBars-1)*(1-tailFrac)
        rawUp=(hiIdx>=tailStart) and riseInto>=lr
        newUp = rawUp and not prevRawUp and upCool==0
        if newUp: upCool=rearmBars
        prevRawUp=rawUp

        if newUp:
            isHigher = lastUpHi is None or wh>lastUpHi
            if isHigher and upCount>0 and (i-upFirstBar)<=maxSpan:
                upCount+=1
            else:
                upCount=1; upFirstBar=i
            lastUpHi=wh
        if upCount>0 and (i-upFirstBar)>maxSpan:
            upCount=0; lastUpHi=None

        if newUp and upCount>=numHighs:
            signals.append(i)
            upCount=0; lastUpHi=None

    trades=[]; inpos_until=-1
    for i0 in signals:
        if i0<=inpos_until: continue
        if i0+1>=len(bars): continue
        cm=M[i0]
        if 840<=cm<960: continue
        if blockOpens and obStart<=cm<obEnd: continue
        entry=O[i0+1]; stop=entry+slPts
        best=entry; trailStop=None; exitP=None; exitbar=len(bars)-1
        for i in range(i0+2,len(bars)):
            h=H[i]; l=L[i]; cm2=M[i]
            best=min(best,l)
            if entry-best>=trailTrig:
                ts=best+trailDist; trailStop=ts if trailStop is None else min(trailStop,ts)
            if 900<=cm2<960:
                exitP=C[i]; exitbar=i; break
            if h>=stop: exitP=stop; exitbar=i; break
            if trailStop is not None and h>=trailStop: exitP=trailStop; exitbar=i; break
        if exitP is None: exitP=C[-1]; exitbar=len(bars)-1
        pnl=(entry-exitP)-slip
        trades.append(dict(pnl=pnl, bars=exitbar-i0, year=bars[i0][0].year))
        inpos_until=exitbar
    return trades, len(signals)

def rep(tr, nsig, label):
    n=len(tr)
    if n==0: print(f"{label}: {nsig} signals, 0 trades taken"); return
    net=sum(t["pnl"] for t in tr); w=[t for t in tr if t["pnl"]>0]
    gw=sum(t["pnl"] for t in w); gl=sum(t["pnl"] for t in tr if t["pnl"]<=0)
    pf=gw/abs(gl) if gl else 99; ab=sum(t["bars"] for t in tr)/n
    print(f"{label}: {n} tr (of {nsig} sig)  net {net:.0f} (${net*2:.0f})  PF {pf:.2f}  win {len(w)/n*100:.0f}%  avgbars {ab:.0f}")

BASE=dict(vBars=60, tailFrac=0.20, legAtrMult=2.5, legAtrLen=14, legMinAbs=12.0, rearmBars=20,
          numHighs=4, maxSpanBars=120, slPts=150.0, trailTrig=70.0, trailDist=30.0,
          openStartCT=450, openEndCT=570, blockOpens=True, slip=0.0)

if __name__=="__main__":
    br=load(RECENT, None)
    print(f"RECENT {len(br)} bars {br[0][0].date()}->{br[-1][0].date()}  (N=4 short-only)")
    for slip in (0.0,1.0):
        for sl in [100,150,200]:
            tr,nsig=run(br, dict(BASE, slPts=float(sl), slip=slip))
            rep(tr, nsig, f"  3wk SL{sl} slip{slip}")
    print()
    b5=load(CSV5, None)
    print(f"5YR {len(b5):,} bars (detecting, heavy)...")
    for slip in (0.0,1.0):
        for sl in [100,150,200]:
            tr,nsig=run(b5, dict(BASE, slPts=float(sl), slip=slip))
            rep(tr, nsig, f"  5yr SL{sl} slip{slip}")
    print()
    tr,nsig=run(b5, dict(BASE, slPts=150.0, slip=0.0))
    yr=defaultdict(lambda:[0,0.0])
    for t in tr: yr[t["year"]][0]+=1; yr[t["year"]][1]+=t["pnl"]
    print("PER-YEAR (SL150 raw):")
    for y in sorted(yr): print(f"  {y}  {yr[y][0]:>4} tr  {yr[y][1]:>8.0f}")
