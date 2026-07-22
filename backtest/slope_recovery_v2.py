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

def run(bars,p):
    lookback=10; dojiPct=10.0
    armLevel=p.get("armLevel",-11.0)
    recovLevel=p.get("recovLevel",-5.0)
    stopSlope=p.get("stopSlope",-11.0)
    trailTrig=p.get("trailTrigger",100.0)
    trailDist=p.get("trailDist",70.0)
    maxSL=p.get("maxSL",0.0)
    slip=p.get("slip",0.0)
    slopeBuf=[]; legSlope=None; armed=False
    inTrade=False; entry=None; best=None; trailStop=None; ebar=None; edt=None
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
            den=n*sx2-sx*sx; legSlope=round((n*sxy-sx*sy)/den,2) if den else 0.0
        if inTrade:
            best=max(best,h)
            if best-entry>=trailTrig:
                ts=best-trailDist; trailStop=ts if trailStop is None else max(trailStop,ts)
            er=None; ep=None
            if maxSL>0 and l<=entry-maxSL: er="SL"; ep=entry-maxSL
            elif trailStop is not None and l<=trailStop: er="TRAIL"; ep=trailStop
            elif eodHard: er="EODHARD"; ep=c
            elif legSlope is not None and legSlope<=stopSlope: er="SLOPESTOP"; ep=c
            if er:
                trades.append(dict(entryDt=edt,exitDt=dt,pts=(ep-entry)-slip,bars=bi-ebar,
                                   mfe=best-entry,reason=er))
                inTrade=False; entry=None; best=None; trailStop=None; armed=False
        if not inTrade and legSlope is not None and not eodHard and not blocked(ctm,p):
            if legSlope<=armLevel: armed=True
            if armed and legSlope>=recovLevel:
                inTrade=True; entry=c; best=c; trailStop=None; ebar=bi; edt=dt; armed=False
    return trades

def summ(tr,label):
    n=len(tr)
    if n==0: print(f"{label:<24} 0 trades"); return 0,0
    net=sum(t["pts"] for t in tr); w=[t for t in tr if t["pts"]>0]
    gw=sum(t["pts"] for t in w); gl=sum(t["pts"] for t in tr if t["pts"]<=0)
    pf=gw/abs(gl) if gl else 99; avgb=sum(t["bars"] for t in tr)/n
    byr=defaultdict(lambda:[0,0.0])
    for t in tr: byr[t["reason"]][0]+=1; byr[t["reason"]][1]+=t["pts"]
    rs=" ".join(f"{r}:{byr[r][0]}" for r in byr)
    print(f"{label:<24} n{n:>4} net{net:>7.0f} PF{pf:>5.2f} win{len(w)/n*100:>3.0f}% "
          f"bars{avgb:>5.0f}({avgb/60:.1f}h) big{max(t['pts'] for t in tr):>5.0f} worst{min(t['pts'] for t in tr):>6.0f}")
    return net,pf

if __name__=="__main__":
    print("loading..."); b5=load(CSV5); brc=load(RECENT)
    print(f"5yr {len(b5):,}  recent {len(brc)}\n")
    blk=dict(blkNY=True,blkLN=True,blkEOD=True,blkON=True)
    base=dict(blk,armLevel=-11.0,recovLevel=-5.0,trailTrigger=100.0,trailDist=70.0)

    print("=== STOP-SLOPE BAND SWEEP (wide trail 100/70) 5yr+OOS ===")
    for ss in [-8,-9,-10,-11]:
        cfg=dict(base,stopSlope=float(ss))
        n5,p5=summ(run(b5,cfg), f"stop{ss}  5yr")
        no,po=summ(run(brc,cfg),f"stop{ss}  OOS")
        print()

    print("=== WIDE TRAIL SWEEP (stop-9) 5yr+OOS ===")
    for tg,ds in [(80,60),(100,70),(120,90),(150,110)]:
        cfg=dict(base,stopSlope=-9.0,trailTrigger=float(tg),trailDist=float(ds))
        summ(run(b5,cfg), f"trail{tg}/{ds} 5yr")
        summ(run(brc,cfg),f"trail{tg}/{ds} OOS")
        print()
