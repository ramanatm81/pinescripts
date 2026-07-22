import csv
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

def blocked(ctm,p):
    if p.get("blkNY") and 510<=ctm<570: return True
    if p.get("blkLN") and 120<=ctm<180: return True
    if p.get("blkEOD") and 840<=ctm<900: return True
    if p.get("blkON") and (ctm>=1200 or ctm<60): return True
    return False

def ols(buf):
    n=len(buf); sx=sy=sxy=sx2=0.0
    for i in range(n):
        x=float(i); y=buf[i]; sx+=x; sy+=y; sxy+=x*y; sx2+=x*x
    den=n*sx2-sx*sx
    return (n*sxy-sx*sy)/den if den else 0.0

def run(bars,p):
    fastLen=p.get("fastLen",10); slowLen=p["slowLen"]; dojiPct=10.0
    slowUp   =p.get("slowUp",0.0)
    slowExit =p.get("slowExit",0.0)
    pbLevel  =p.get("pbLevel",-3.0)
    recovLevel=p.get("recovLevel",0.0)
    maxSL    =p.get("maxSL",100.0)
    slip     =p.get("slip",0.0)
    fastBuf=[]; slowBuf=[]; fast=None; slow=None
    inTrade=False; entry=None; ebar=None; edt=None; best=None; armed=False
    trades=[]
    for bi,(dt,o,h,l,c,ctm) in enumerate(bars):
        eodHard=900<=ctm<960
        rng=h-l; bpc=(abs(c-o)/rng*100.0) if rng>0 else 0.0; isDoji=bpc<dojiPct
        fast=None; slow=None
        if not eodHard and not isDoji:
            fastBuf.append(c); slowBuf.append(c)
            if len(fastBuf)>fastLen: fastBuf.pop(0)
            if len(slowBuf)>slowLen: slowBuf.pop(0)
        if len(fastBuf)==fastLen: fast=round(ols(fastBuf),2)
        if len(slowBuf)==slowLen: slow=round(ols(slowBuf),3)

        if inTrade:
            best=max(best,h)
            er=None; ep=None
            if maxSL>0 and l<=entry-maxSL: er="SL"; ep=entry-maxSL
            elif eodHard: er="EODHARD"; ep=c
            elif slow is not None and slow<=slowExit: er="TRENDEND"; ep=c
            if er:
                trades.append(dict(entryDt=edt,exitDt=dt,pts=(ep-entry)-slip,bars=bi-ebar,
                                   mfe=best-entry,reason=er))
                inTrade=False; entry=None; best=None; armed=False

        if not inTrade and fast is not None and slow is not None and not eodHard and not blocked(ctm,p):
            if slow>slowUp:
                if fast<=pbLevel: armed=True
                if armed and fast>=recovLevel:
                    inTrade=True; entry=c; best=c; ebar=bi; edt=dt; armed=False
            else:
                armed=False
    return trades

def summ(tr,label,reason=False):
    n=len(tr)
    if n==0: print(f"{label:<26} 0 trades"); return 0
    net=sum(t["pts"] for t in tr); w=[t for t in tr if t["pts"]>0]
    gw=sum(t["pts"] for t in w); gl=sum(t["pts"] for t in tr if t["pts"]<=0)
    pf=gw/abs(gl) if gl else 99; avgb=sum(t["bars"] for t in tr)/n
    print(f"{label:<26} n{n:>4} net{net:>7.0f} PF{pf:>5.2f} win{len(w)/n*100:>3.0f}% "
          f"aw{gw/len(w) if w else 0:>5.0f} al{gl/(n-len(w)) if n-len(w) else 0:>6.0f} "
          f"bars{avgb:>5.0f}({avgb/60:.1f}h) big{max(t['pts'] for t in tr):>5.0f}")
    if reason:
        byr=defaultdict(lambda:[0,0.0])
        for t in tr: byr[t["reason"]][0]+=1; byr[t["reason"]][1]+=t["pts"]
        for r in sorted(byr,key=lambda k:-byr[k][1]): print(f"      {r:<9}{byr[r][0]:>5}tr {byr[r][1]:>8.0f}")
    return net

if __name__=="__main__":
    print("loading..."); b5=load(CSV5); brc=load(RECENT)
    print(f"5yr {len(b5):,} bars  recent {len(brc)} bars\n")
    blk=dict(blkNY=True,blkLN=True,blkEOD=True,blkON=True)

    print("=== SLOW LOOKBACK SWEEP (fast10, pb-3 recov0, maxSL100) on 5yr ===")
    for sl in [30,50,60,80,100,150]:
        summ(run(b5,dict(blk,slowLen=sl,pbLevel=-3.0,recovLevel=0.0)),f"slow{sl}")
    print()
    print("=== PULLBACK/RECOVERY SWEEP (slow60) on 5yr ===")
    for pb in [-2,-4,-6]:
        for rc in [-1,0,2]:
            summ(run(b5,dict(blk,slowLen=60,pbLevel=float(pb),recovLevel=float(rc))),f"pb{pb} recov{rc:+d}")
    print()
    print("=== 5yr vs OUT-OF-SAMPLE for a few configs ===")
    for sl,pb,rc in [(60,-3,0),(80,-4,0),(50,-3,0),(100,-4,0)]:
        cfg=dict(blk,slowLen=sl,pbLevel=float(pb),recovLevel=float(rc))
        print(f"-- slow{sl} pb{pb} recov{rc} --")
        summ(run(b5,cfg), "  5yr")
        summ(run(brc,cfg),"  OOS recent")
