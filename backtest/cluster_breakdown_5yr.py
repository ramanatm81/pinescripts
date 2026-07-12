import csv, sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import Counter

CSV="/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
LDN=ZoneInfo("Europe/London")
CT=ZoneInfo("America/Chicago")
KSIGMA=2.0

P=dict(lookback=10, dojiPct=10.0, clWindow=10, clNeeded=6, lbBand=10,
       srHalfWidth=10, srZoneWidth=25.0, clSlPts=70.0, revSlope=2.0, slPts=70.0,
       trailArm=80.0, trailGap=40.0, cooldownBars=10,
       enableShort=True, enableLong=True, enableTrail=True)

def load():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
                v=float(row.get("Volume") or row.get("volume") or 0.0)
            except: continue
            dt=datetime.fromisoformat(row["time"])
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            bars.append((dt,o,h,l,c,v))
    return bars

def vwap_bands(bars):
    out=[]; curday=None; cumV=cumPV=cumPPV=0.0
    for dt,o,h,l,c,v in bars:
        d=dt.astimezone(LDN).date()
        if d!=curday: curday=d; cumV=cumPV=cumPPV=0.0
        tp=(h+l+c)/3.0; vv=v if v>0 else 1.0
        cumV+=vv; cumPV+=tp*vv; cumPPV+=tp*tp*vv
        mean=cumPV/cumV; var=max(cumPPV/cumV-mean*mean,0.0); sd=var**0.5
        out.append((mean, mean+KSIGMA*sd, mean-KSIGMA*sd))
    return out

def run(bars, bands, p):
    lookback=p["lookback"]; dojiPct=p["dojiPct"]; clW=p["clWindow"]; clN=p["clNeeded"]
    lbBand=p["lbBand"]; hw=p["srHalfWidth"]; zw=p["srZoneWidth"]
    clSl=p["clSlPts"]; revSlope=p["revSlope"]; slPts=p["slPts"]
    trailArm=p["trailArm"]; trailGap=p["trailGap"]; cool=p["cooldownBars"]
    enS=p["enableShort"]; enL=p["enableLong"]; enT=p["enableTrail"]

    highs=[b[2] for b in bars]; lows=[b[3] for b in bars]
    los=[bd[2] for bd in bands]

    trades=[]; slopeBuf=[]
    pos=0; entry=None; best=None; cd=0; entryDt=None; mfe=0.0
    lastFH=None; lastFL=None
    piercedHist=[]; loHist=[]; breakdownHist=[]
    prevLdnDay=None

    for i,(dt,o,h,l,c,v) in enumerate(bars):
        mean,up,lo=bands[i]
        ct=dt.astimezone(CT); ctm=ct.hour*60+ct.minute
        inRTH = 510<=ctm<900
        eodClose = 900<=ctm<960

        rng=h-l; body=abs(c-o)
        bodyPct=(body/rng*100.0) if rng>0 else 0.0
        isDoji=bodyPct<dojiPct
        if not eodClose and not isDoji:
            slopeBuf.append(c)
            if len(slopeBuf)>lookback: slopeBuf.pop(0)
        legSlope=None
        if len(slopeBuf)==lookback:
            n=lookback; sx=sy=sxy=sxx=0.0
            for k in range(n):
                x=float(k); y=slopeBuf[k]; sx+=x; sy+=y; sxy+=x*y; sxx+=x*x
            den=n*sxx-sx*sx
            legSlope=round((n*sxy-sx*sy)/den,2) if den!=0 else 0.0

        bandsFormed=(up-lo)>=1.0

        loHist.append(lo)
        loPrev=loHist[-1-lbBand] if len(loHist)>lbBand else None
        bandFalling = bandsFormed and (loPrev is not None) and lo<loPrev

        if i>=2*hw:
            ctr=i-hw
            ch=highs[ctr]
            if all(ch>highs[j] for j in range(i-2*hw,ctr)) and all(ch>highs[j] for j in range(ctr+1,i+1)):
                lastFH=ch
            cl=lows[ctr]
            if all(cl<lows[j] for j in range(i-2*hw,ctr)) and all(cl<lows[j] for j in range(ctr+1,i+1)):
                lastFL=cl
        supBelowPivots=(lastFL is not None) and (lastFH is not None) and bandsFormed and (lo < lastFL-zw)

        pierced = 1 if (bandsFormed and l<lo) else 0
        piercedHist.append(pierced)
        pcount=sum(piercedHist[-clW:])
        breakdown = bandsFormed and pcount>=clN
        breakdownHist.append(1 if breakdown else 0)
        recentCluster = breakdown or (max(breakdownHist[-clW:]) if breakdownHist else 0)>0

        newLdn = dt.astimezone(LDN).date()!=prevLdnDay; prevLdnDay=dt.astimezone(LDN).date()

        if pos!=0 and eodClose:
            pnl=(entry-c) if pos<0 else (c-entry)
            trades.append((pos,entry,c,pnl,"EOD",entryDt,mfe))
            pos=0; entry=None; best=None; cd=0

        if cd>0 and pos==0: cd-=1

        shortSetup = breakdown and bandFalling and supBelowPivots and (c<lo)
        canEnter = pos==0 and cd==0 and inRTH and bandsFormed and legSlope is not None
        shortSignal = enS and canEnter and shortSetup
        longSignal  = enL and canEnter and recentCluster and (c>lo) and legSlope>=revSlope

        if pos==0 and shortSignal:
            pos=-1; entry=c; best=c; entryDt=dt; mfe=0.0
        elif pos==0 and longSignal:
            pos=1; entry=c; best=c; entryDt=dt; mfe=0.0

        if pos<0:
            best=min(best,c) if best is not None else c
            mfe=max(mfe, entry-l)
        elif pos>0:
            best=max(best,c) if best is not None else c
            mfe=max(mfe, h-entry)

        if pos!=0:
            longArmed  = pos>0 and best is not None and (best-entry)>=trailArm
            shortArmed = pos<0 and best is not None and (entry-best)>=trailArm
            longTrail  = (best-trailGap) if (enT and longArmed) else None
            shortTrail = (best+trailGap) if (enT and shortArmed) else None

            if pos<0:
                if not shortSetup:
                    pnl=entry-c; trades.append((pos,entry,c,pnl,"setup broke",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
                elif shortTrail is not None and c>=shortTrail:
                    pnl=entry-c; trades.append((pos,entry,c,pnl,"trail",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
                elif h>=entry+clSl:
                    fill=entry+clSl; pnl=entry-fill; trades.append((pos,entry,fill,pnl,"SL",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
            elif pos>0:
                if longTrail is not None and c<=longTrail:
                    pnl=c-entry; trades.append((pos,entry,c,pnl,"trail",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
                elif l<=entry-slPts:
                    fill=entry-slPts; pnl=fill-entry; trades.append((pos,entry,fill,pnl,"SL",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool

    return trades

def summ(trs, slip, years):
    p=[t[3]-slip for t in trs]; n=len(p)
    if n==0: return (0,0,0,0,[0]*len(years),0)
    w=sum(1 for x in p if x>0); gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    yl=[]; pos=0
    for y in years:
        yy=round(sum(t[3]-slip for t in trs if t[5].year==y))
        if yy>0: pos+=1
        yl.append(yy)
    return (round(sum(p)), n, round(gp/gl,2) if gl>0 else 999, round(100*w/n,1), yl, pos)

if __name__=="__main__":
    print("loading + vwap bands...")
    bars=load(); bands=vwap_bands(bars)
    years=[2021,2022,2023,2024,2025,2026]
    print(f"bars {len(bars):,}")
    trs=run(bars,bands,P)
    longs=[t for t in trs if t[0]>0]; shorts=[t for t in trs if t[0]<0]
    print(f"total trades {len(trs)}  longs {len(longs)}  shorts {len(shorts)}")
    print("exit mix:", dict(Counter(t[4] for t in trs)))
    for label,sub in (("ALL",trs),("SHORT",shorts),("LONG",longs)):
        for slip in (0.0,1.0):
            pnl,n,pf,win,yl,pos=summ(sub,slip,years)
            print(f"{label:6} slip{slip} | pnl {pnl:>7} n {n:>5} pf {pf:>5} win {win:>5} | {pos}/6 | {yl}")
