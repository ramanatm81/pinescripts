import csv, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

CSV5 = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
RECENT = "/Users/maheshk81/Downloads/data.csv"

def load(path):
    bars=[]
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            t=row.get("time") or row.get("Date and time")
            if not t: continue
            dt=datetime.fromisoformat(t).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute))
    return bars

def blocked(ctm, p):
    if p.get("blkNY") and 510<=ctm<570: return True
    if p.get("blkLN") and 120<=ctm<180: return True
    if p.get("blkEOD") and 840<=ctm<900: return True
    if p.get("blkON") and (ctm>=1200 or ctm<60): return True
    return False

def run(bars, p):
    lookback=10; dojiPct=10.0
    entrySlope=p["entrySlope"]
    exitSlope =p["exitSlope"]
    maxSL     =p.get("maxSL",0.0)
    slip      =p.get("slip",0.0)
    minHoldBars=p.get("minHoldBars",0)
    slopeBuf=[]; legSlope=None
    inTrade=False; entryPrice=None; entryBar=None; entryDt=None; bestPrice=None
    trades=[]
    for bi,(dt,o,h,l,c,ctm) in enumerate(bars):
        eodHard=900<=ctm<960
        rng=h-l; bpc=(abs(c-o)/rng*100.0) if rng>0 else 0.0; isDoji=bpc<dojiPct
        legSlope=None
        if not eodHard and not isDoji:
            slopeBuf.append(c)
            if len(slopeBuf)>lookback: slopeBuf.pop(0)
        if len(slopeBuf)==lookback:
            n=lookback; sx=sy=sxy=sx2=0.0
            for i in range(n):
                x=float(i); y=slopeBuf[i]; sx+=x; sy+=y; sxy+=x*y; sx2+=x*x
            den=n*sx2-sx*sx; legSlope=round((n*sxy-sx*sy)/den,2) if den!=0 else 0.0

        if inTrade:
            bestPrice=max(bestPrice,h)
            held=bi-entryBar
            er=None; ep=None
            if maxSL>0 and l<=entryPrice-maxSL: er="SL"; ep=entryPrice-maxSL
            elif eodHard: er="EODHARD"; ep=c
            elif held>=minHoldBars and legSlope is not None and legSlope<=exitSlope: er="SLOPEDN"; ep=c
            if er:
                trades.append(dict(entryDt=entryDt,exitDt=dt,pts=(ep-entryPrice)-slip,
                                   bars=held,mfe=bestPrice-entryPrice,reason=er))
                inTrade=False; entryPrice=None; bestPrice=None

        if not inTrade and legSlope is not None and not eodHard and not blocked(ctm,p):
            if legSlope>=entrySlope:
                inTrade=True; entryPrice=c; bestPrice=c; entryBar=bi; entryDt=dt
    return trades

def summ(tr,label,show_reason=False):
    n=len(tr)
    if n==0: print(f"{label:<40} 0 trades"); return None
    net=sum(t["pts"] for t in tr); w=[t for t in tr if t["pts"]>0]
    gw=sum(t["pts"] for t in w); gl=sum(t["pts"] for t in tr if t["pts"]<=0)
    pf=gw/abs(gl) if gl else 99
    avgb=sum(t["bars"] for t in tr)/n
    aw=gw/len(w) if w else 0; al=gl/(n-len(w)) if n-len(w) else 0
    print(f"{label:<40} n{n:>4} net{net:>7.0f} PF{pf:>5.2f} win{len(w)/n*100:>3.0f}% "
          f"aw{aw:>5.0f} al{al:>6.0f} bars{avgb:>5.0f}({avgb/60:.1f}h) big{max(t['pts'] for t in tr):>5.0f}")
    if show_reason:
        byr=defaultdict(lambda:[0,0.0])
        for t in tr: byr[t["reason"]][0]+=1; byr[t["reason"]][1]+=t["pts"]
        for r in sorted(byr,key=lambda k:-byr[k][1]): print(f"      {r:<9}{byr[r][0]:>5}tr {byr[r][1]:>8.0f}")
    return net

if __name__=="__main__":
    print("loading..."); b5=load(CSV5); brc=load(RECENT)
    print(f"5yr {len(b5):,} bars {b5[0][0].date()}->{b5[-1][0].date()}")
    print(f"recent {len(brc)} bars {brc[0][0].date()}->{brc[-1][0].date()}\n")
    blk=dict(blkNY=True,blkLN=True,blkEOD=True,blkON=True)

    print("=== ENTRY/EXIT SLOPE SWEEP on 5yr (blocks on, maxSL=100) ===")
    for es in [2,4,6,8,11]:
        for xs in [-2,0,2]:
            summ(run(b5,dict(blk,entrySlope=float(es),exitSlope=float(xs),maxSL=100.0)),
                 f"entry+{es} exit{xs:+d}")
    print()
    print("=== BEST-ish configs: 5yr vs OUT-OF-SAMPLE recent ===")
    for es,xs in [(4,0),(6,0),(6,2),(8,0)]:
        cfg=dict(blk,entrySlope=float(es),exitSlope=float(xs),maxSL=100.0)
        print(f"-- entry+{es} exit{xs:+d} --")
        summ(run(b5,cfg),  "  5yr        ")
        summ(run(brc,cfg), "  recent(OOS)")
