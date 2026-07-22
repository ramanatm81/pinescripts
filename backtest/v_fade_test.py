import csv, math
from datetime import datetime, timezone, timedelta

RECENT = "/Users/maheshk81/Downloads/data.csv"

def load(path):
    bars=[]
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            t=r.get("time")
            if not t: continue
            try: o=float(r["open"]);h=float(r["high"]);l=float(r["low"]);c=float(r["close"])
            except: continue
            dt=datetime.fromisoformat(t).astimezone(timezone(timedelta(hours=1)))
            bars.append((dt,o,h,l,c))
    return bars

def atr(H,L,C,i,n):
    s=0.0
    for k in range(i-n+1,i+1): s+=max(H[k]-L[k],abs(H[k]-C[k-1]),abs(L[k]-C[k-1]))
    return s/n

def detect(bars, p):
    H=[b[2] for b in bars]; L=[b[3] for b in bars]; C=[b[4] for b in bars]
    vBars=p["vBars"]; legMinAbs=p["legMinAbs"]; legAtrMult=2.0; legAtrLen=14
    symMax=3.0; apexTol=p["apexTol"]; newApexPts=15.0
    minLegAngle=p["minLegAngle"]; maxAngleGap=p["maxAngleGap"]; useGeom=p["useGeom"]
    lastVlow=None;vCool=0;lastIVhigh=None;ivCool=0
    ev=[]
    for i in range(vBars,len(bars)):
        vCool=max(0,vCool-1);ivCool=max(0,ivCool-1)
        wl=min(L[i-vBars+1:i+1]); wh=max(H[i-vBars+1:i+1])
        loA=hiA=i
        for k in range(i-vBars+1,i+1):
            if L[k]<=wl: loA=k
            if H[k]>=wh: hiA=k
        loIdx=loA-(i-vBars+1); hiIdx=hiA-(i-vBars+1)
        fc=C[i-vBars+1]; nc=C[i]; a=atr(H,L,C,i,legAtrLen); lr=max(legAtrMult*a,legMinAbs); ag=a if a>0 else 1
        dL=fc-wl;uL=nc-wl;uL2=wh-fc;dL2=wh-nc; ctr=(vBars-1)/2.0
        loN=abs(loIdx-ctr)<=apexTol*vBars; hiN=abs(hiIdx-ctr)<=apexTol*vBars
        vSym=min(dL,uL)>0 and max(dL,uL)/min(dL,uL)<=symMax
        ivSym=min(uL2,dL2)>0 and max(uL2,dL2)/min(uL2,dL2)<=symMax
        vLA=math.degrees(math.atan((dL/max(1,loIdx))/ag)); vRA=math.degrees(math.atan((uL/max(1,vBars-1-loIdx))/ag))
        ivLA=math.degrees(math.atan((uL2/max(1,hiIdx))/ag)); ivRA=math.degrees(math.atan((dL2/max(1,vBars-1-hiIdx))/ag))
        vG=(not useGeom) or (vLA>=minLegAngle and vRA>=minLegAngle and abs(vLA-vRA)<=maxAngleGap)
        ivG=(not useGeom) or (ivLA>=minLegAngle and ivRA>=minLegAngle and abs(ivLA-ivRA)<=maxAngleGap)
        isV=dL>=lr and uL>=lr and loN and vSym and vG
        isIV=uL2>=lr and dL2>=lr and hiN and ivSym and ivG
        vFresh=lastVlow is None or wl<=lastVlow-newApexPts or vCool==0
        ivFresh=lastIVhigh is None or wh>=lastIVhigh+newApexPts or ivCool==0
        if isV and vFresh:
            ev.append(dict(kind="V", bar=i, close=nc, apex=wl)); lastVlow=wl;vCool=vBars
        if isIV and ivFresh:
            ev.append(dict(kind="IV", bar=i, close=nc, apex=wh)); lastIVhigh=wh;ivCool=vBars
    return ev

def trade(bars, ev, p):
    H=[b[2] for b in bars]; L=[b[3] for b in bars]; C=[b[4] for b in bars]
    stopBeyond=p["stopBeyond"]; trailTrig=p["trailTrig"]; trailDist=p["trailDist"]; slip=p["slip"]
    trades=[]
    for e in ev:
        i0=e["bar"]; entry=e["close"]
        # trade WITH the reversal: V(bottom)->LONG stop below the apex low; inverse-V(top)->SHORT
        # stop above the apex high. Stop sits stopBeyond pts beyond the reversal extreme.
        if e["kind"]=="V":
            dirn=1; stop=e["apex"]-stopBeyond
        else:
            dirn=-1; stop=e["apex"]+stopBeyond
        best=entry; trailStop=None; exitP=None; reason=None
        for i in range(i0+1, len(bars)):
            h=H[i]; l=L[i]; c=C[i]
            if dirn==1:
                best=max(best,h)
                if best-entry>=trailTrig:
                    ts=best-trailDist; trailStop=ts if trailStop is None else max(trailStop,ts)
                if l<=stop: exitP=stop; reason="STOP"; break
                if trailStop is not None and l<=trailStop: exitP=trailStop; reason="TRAIL"; break
            else:
                best=min(best,l)
                if entry-best>=trailTrig:
                    ts=best+trailDist; trailStop=ts if trailStop is None else min(trailStop,ts)
                if h>=stop: exitP=stop; reason="STOP"; break
                if trailStop is not None and h>=trailStop: exitP=trailStop; reason="TRAIL"; break
        if exitP is None:
            exitP=C[-1]; reason="EOD"; i=len(bars)-1
        pnl=((exitP-entry) if dirn==1 else (entry-exitP))-slip
        trades.append(dict(kind=e["kind"], dirn=dirn, entry=entry, exit=exitP, pnl=pnl, reason=reason, bars=i-i0))
    return trades

def summ(tr,label):
    n=len(tr)
    if n==0: print(label,"0 trades"); return
    net=sum(t["pnl"] for t in tr); w=[t for t in tr if t["pnl"]>0]
    gw=sum(t["pnl"] for t in w); gl=sum(t["pnl"] for t in tr if t["pnl"]<=0)
    pf=gw/abs(gl) if gl else 99; ab=sum(t["bars"] for t in tr)/n
    print(f"{label}: {n} tr  net {net:.0f} pts (${net*2:.0f})  PF {pf:.2f}  win {len(w)/n*100:.0f}%  avgbars {ab:.0f}  big {max(t['pnl'] for t in tr):.0f} worst {min(t['pnl'] for t in tr):.0f}")
    from collections import Counter
    by={}
    for t in tr:
        k=t["kind"]; by.setdefault(k,[0,0.0]); by[k][0]+=1; by[k][1]+=t["pnl"]
    for k,(cnt,pp) in by.items(): print(f"    {'IV->SHORT' if k=='IV' else 'V->LONG'}: {cnt} tr  {pp:.0f} pts")

if __name__=="__main__":
    bars=load(RECENT)
    print(f"{len(bars)} bars {bars[0][0].date()} -> {bars[-1][0].date()}")
    det=dict(vBars=60, legMinAbs=80.0, apexTol=0.20, minLegAngle=9.0, maxAngleGap=6.0, useGeom=True)
    ev=detect(bars, det)
    nv=sum(1 for e in ev if e["kind"]=="V"); niv=sum(1 for e in ev if e["kind"]=="IV")
    print(f"detected: {nv} V (->LONG), {niv} inverse-V (->SHORT)\n")
    for slip in (0.0,1.0):
        base=dict(stopBeyond=50.0, trailTrig=70.0, trailDist=20.0, slip=slip)
        tr=trade(bars, ev, base)
        summ(tr, f"WITH-reversal V/^ stop50 trail70/20 slip{slip}")
    print()
    print("stopBeyond sweep (raw):")
    for sb in [30,50,70,100]:
        tr=trade(bars, ev, dict(stopBeyond=float(sb), trailTrig=70.0, trailDist=20.0, slip=0.0))
        summ(tr, f"  stop{sb}")
    print()
    print("trail sweep (stop50, raw):")
    for tg,td in [(70,20),(50,15),(100,30),(70,40)]:
        tr=trade(bars, ev, dict(stopBeyond=50.0, trailTrig=float(tg), trailDist=float(td), slip=0.0))
        summ(tr, f"  trail{tg}/{td}")
