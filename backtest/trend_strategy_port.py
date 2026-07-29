import csv, os, sys, math
from datetime import datetime, timezone, timedelta

DATA = os.environ.get("BACKTEST_DATA", "/Users/maheshk81/Downloads/data.csv")

P = dict(
    winMin=60, winMax=240, winStep=10, maxWinN=130,
    runMinPts=150.0, minR2=0.75, pickBest=True,
    pullbackPts=150.0, pullbackFrac=0.5, reEntryFrac=0.7,
    confirmMins=0, confirmAdvPts=40.0, adverseStopPts=40.0, provenPts=80.0,
    cancelCool=10, enableDblEx=True, dbAwayPts=30.0, dbTolPts=8.0,
    enableStale=False, staleBars=20, staleFavPts=30.0,
    tradeLong=True, tradeShort=True,
    enableSessFilt=True, blockStartHr=23, blockEndHr=12,
    enableEod=True, eodHour=21, reopenHour=23,
    slip=0.0,
)

LONDON = timezone(timedelta(hours=1))

def load(path):
    t=[]; o=[]; h=[]; l=[]; c=[]
    with open(path) as f:
        for r in csv.DictReader(f):
            try:
                o.append(float(r["open"])); h.append(float(r["high"]))
                l.append(float(r["low"])); c.append(float(r["close"]))
                t.append(r["time"])
            except (ValueError, KeyError):
                continue
    return t,o,h,l,c

def parse_hour(ts, tz_offset_hours=None):
    dt=datetime.fromisoformat(ts)
    return dt

def ols_scan(c, i, Nw):
    if i < Nw-1: return None,None
    yRef=c[i-(Nw-1)]
    sx=sy=sxx=syy=sxy=0.0
    for k in range(Nw):
        x=float(Nw-1-k)
        y=c[i-k]-yRef
        sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y
    fN=float(Nw)
    varX=sxx-sx*sx/fN; varY=syy-sy*sy/fN; covXY=sxy-sx*sy/fN
    if varX>0 and varY>0:
        return covXY/varX, (covXY*covXY)/(varX*varY)
    return None,None

def hour_of(ts):
    return datetime.fromisoformat(ts).hour
def minute_of(ts):
    return datetime.fromisoformat(ts).minute

def run(t,o,h,l,c,P):
    n=len(c)
    tState=0; tDir=0; tWinN=None; tExtreme=None; tStartPx=None
    tLockDir=0; tLockExt=None; tLockTrv=None
    tDotBar=None; tDotPrice=None; tCancelDir=0; tCancelBar=None
    tMovedAway=False; tPullExt=None

    pos=0; entryPx=None; entryIdx=None
    pending=None
    trades=[]

    for i in range(n):
        ts=t[i]; hi=h[i]; lo=l[i]; cl=c[i]; op=o[i]
        nowMin=hour_of(ts)*60+minute_of(ts)
        flatMin=P["eodHour"]*60; openMin=P["reopenHour"]*60
        if flatMin<=openMin:
            inWin = nowMin>=flatMin and nowMin<openMin
        else:
            inWin = nowMin>=flatMin or nowMin<openMin
        eodClosed = P["enableEod"] and inWin

        if pending is not None:
            act,pdir,reason=pending
            if act=="enter":
                pos=pdir; entryPx=op; entryIdx=i
            elif act=="exit":
                pnl=(op-entryPx)*pos - P["slip"]
                trades.append(dict(eidx=entryIdx,xidx=i,dir=pos,entry=entryPx,exit=op,pnl=pnl,reason=reason,
                                   et=t[entryIdx],xt=ts))
                pos=0; entryPx=None; entryIdx=None
            pending=None

        gap_min=(datetime.fromisoformat(ts)-datetime.fromisoformat(t[i-1])).total_seconds()/60.0 if i>0 else 0
        windowEdge = eodClosed and i>0 and not (
            (lambda pm: (pm>=flatMin and pm<openMin) if flatMin<=openMin else (pm>=flatMin or pm<openMin))(
                hour_of(t[i-1])*60+minute_of(t[i-1])))
        gapEdge = P["enableEod"] and gap_min>60
        eodFlatEdge = windowEdge or gapEdge

        trendStart=False; startDir=0; startN=None
        trendBreak=False; trendCancel=False; dblExit=False

        if tLockDir!=0 and tLockExt is not None:
            need=P["reEntryFrac"]*tLockTrv
            if tLockDir<0 and hi>=tLockExt+need: tLockDir=0
            elif tLockDir>0 and lo<=tLockExt-need: tLockDir=0
        if tCancelDir!=0 and (tCancelBar is None or i-tCancelBar>=P["cancelCool"]):
            tCancelDir=0

        if eodFlatEdge and tState==1:
            trendBreak=True; tState=0; tDir=0; tWinN=None; tExtreme=None

        if tState==0:
            dS=dR=None; dN=None
            wmax=min(P["winMax"],4990)
            Nw=P["winMin"]
            while Nw<=wmax:
                if Nw>=3 and i>=Nw-1:
                    s,r2=ols_scan(c,i,Nw)
                    if s is not None and abs(s)*float(Nw-1)>=P["runMinPts"] and r2>=P["minR2"]:
                        d=1 if s>0 else -1
                        if d!=tLockDir and d!=tCancelDir and (dN is None or (P["pickBest"] and r2>dR)):
                            dS=s; dR=r2; dN=Nw
                Nw+=P["winStep"]
            if dN is not None and not eodClosed:
                tState=1; tDir=1 if dS>0 else -1; tWinN=dN
                tStartPx=c[i-(dN-1)]
                tExtreme=hi if tDir>0 else lo
                trendStart=True; startDir=tDir; startN=dN
                tDotBar=i; tDotPrice=cl; tMovedAway=False; tPullExt=None
        else:
            prevExt=tExtreme
            tExtreme=max(tExtreme,hi) if tDir>0 else min(tExtreme,lo)
            newExtreme = (tExtreme>prevExt) if tDir>0 else (tExtreme<prevExt)
            if newExtreme:
                tMovedAway=False; tPullExt=None
            tPullExt = (lo if tDir>0 else hi) if tPullExt is None else (min(tPullExt,lo) if tDir>0 else max(tPullExt,hi))
            offExt = (tExtreme-lo) if tDir>0 else (hi-tExtreme)
            if offExt>=P["dbAwayPts"]: tMovedAway=True
            retestGap = (tExtreme-hi) if tDir>0 else (lo-tExtreme)
            age=i-tDotBar
            adverse = (tDotPrice-lo) if tDir>0 else (hi-tDotPrice)
            confirmCancel = P["confirmMins"]>0 and age>=1 and age<=P["confirmMins"] and adverse>=P["confirmAdvPts"]
            favTravel = (tExtreme-tDotPrice) if tDir>0 else (tDotPrice-tExtreme)
            proven = favTravel>=P["provenPts"]
            adverseStop = P["adverseStopPts"]>0 and age>=1 and not proven and adverse>=P["adverseStopPts"]
            favNow = (cl-tDotPrice) if tDir>0 else (tDotPrice-cl)
            staleCancel = P["enableStale"] and age==P["staleBars"] and favNow<P["staleFavPts"]
            cancel = confirmCancel or adverseStop or staleCancel
            dblDetected = P["enableDblEx"] and proven and tMovedAway and (not newExtreme) and retestGap>=0 and retestGap<=P["dbTolPts"]
            dblExit = dblDetected
            travel=abs(tExtreme-tStartPx)
            effPb=max(P["pullbackPts"],travel*P["pullbackFrac"])
            brokeUp = tDir>0 and cl<tExtreme-effPb
            brokeDn = tDir<0 and cl>tExtreme+effPb
            if cancel:
                trendCancel=True; tCancelDir=tDir; tCancelBar=i
                tState=0; tDir=0; tWinN=None; tExtreme=None
            elif brokeUp or brokeDn or dblExit:
                trendBreak=True; tLockDir=tDir; tLockExt=tExtreme
                tLockTrv=max(abs(tExtreme-tStartPx),1.0)
                tState=0; tDir=0; tWinN=None; tExtreme=None

        sh=hour_of(ts)
        blocked = P["enableSessFilt"] and ((sh>=P["blockStartHr"] and sh<P["blockEndHr"]) if P["blockStartHr"]<=P["blockEndHr"] else (sh>=P["blockStartHr"] or sh<P["blockEndHr"]))
        winNok = P["maxWinN"]<=0 or (startN is not None and startN<=P["maxWinN"])
        takeLong  = trendStart and startDir>0 and P["tradeLong"] and not eodClosed and not blocked and winNok
        takeShort = trendStart and startDir<0 and P["tradeShort"] and not eodClosed and not blocked and winNok

        if pos!=0 and (dblExit or trendBreak or trendCancel):
            reason = "dbl" if dblExit else ("cancel" if trendCancel else "break")
            pending=("exit",None,reason)
        elif pos==0 and (takeLong or takeShort):
            pending=("enter", 1 if takeLong else -1, "entry")

    return trades

if __name__=="__main__":
    t,o,h,l,c=load(DATA)
    trades=run(t,o,h,l,c,P)
    net=sum(x["pnl"] for x in trades)
    L=[x for x in trades if x["dir"]==1]; S=[x for x in trades if x["dir"]==-1]
    from collections import Counter,defaultdict
    print("PORT on",DATA)
    print("  trades",len(trades)," net %.0f pts"%net," win%% %.1f"%(100*sum(1 for x in trades if x["pnl"]>0)/len(trades) if trades else 0))
    print("  LONG %d net %.0f | SHORT %d net %.0f"%(len(L),sum(x["pnl"] for x in L),len(S),sum(x["pnl"] for x in S)))
    by=defaultdict(lambda:[0,0.0])
    for x in trades: by[x["reason"]][0]+=1; by[x["reason"]][1]+=x["pnl"]
    for k,v in sorted(by.items(),key=lambda z:-z[1][1]):
        print("   %-8s %3d  net %.0f"%(k,v[0],v[1]))
