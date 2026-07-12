import sys, statistics as st
from collections import Counter
sys.path.insert(0,'/Users/maheshk81/pinescripts/backtest')
import cluster_breakdown_5yr as m

def run_variant(bars, bands, p):
    lookback=p["lookback"]; dojiPct=p["dojiPct"]; clW=p["clWindow"]; clN=p["clNeeded"]
    lbBand=p["lbBand"]; hw=p["srHalfWidth"]; zw=p["srZoneWidth"]
    clSl=p["clSlPts"]; revSlope=p["revSlope"]; slPts=p["slPts"]
    trailArm=p["trailArm"]; trailGap=p["trailGap"]; cool=p["cooldownBars"]
    enS=p["enableShort"]; enL=p["enableLong"]; enT=p["enableTrail"]
    revShortSlope=p.get("revShortSlope", revSlope)

    from zoneinfo import ZoneInfo
    LDN=ZoneInfo("Europe/London"); CT=ZoneInfo("America/Chicago")
    highs=[b[2] for b in bars]; lows=[b[3] for b in bars]

    trades=[]; slopeBuf=[]
    pos=0; entry=None; best=None; cd=0; entryDt=None; mfe=0.0
    lastFH=None; lastFL=None
    piercedHist=[]; loHist=[]; breakdownHist=[]

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

        if i>=2*hw:
            ctr=i-hw
            ch=highs[ctr]
            if all(ch>highs[j] for j in range(i-2*hw,ctr)) and all(ch>highs[j] for j in range(ctr+1,i+1)):
                lastFH=ch
            cl=lows[ctr]
            if all(cl<lows[j] for j in range(i-2*hw,ctr)) and all(cl<lows[j] for j in range(ctr+1,i+1)):
                lastFL=cl

        pierced = 1 if (bandsFormed and l<lo) else 0
        piercedHist.append(pierced)
        pcount=sum(piercedHist[-clW:])
        breakdown = bandsFormed and pcount>=clN
        breakdownHist.append(1 if breakdown else 0)
        recentCluster = breakdown or (max(breakdownHist[-clW:]) if breakdownHist else 0)>0

        if pos!=0 and eodClose:
            pnl=(entry-c) if pos<0 else (c-entry)
            trades.append((pos,entry,c,pnl,"EOD",entryDt,mfe))
            pos=0; entry=None; best=None; cd=0

        if cd>0 and pos==0: cd-=1

        canEnter = pos==0 and cd==0 and inRTH and bandsFormed and legSlope is not None
        longSignal  = enL and canEnter and recentCluster and (c>lo) and legSlope>=revSlope
        shortSignal = enS and canEnter and recentCluster and (c<lo) and legSlope<=-revShortSlope

        if pos==0 and longSignal:
            pos=1; entry=c; best=c; entryDt=dt; mfe=0.0
        elif pos==0 and shortSignal:
            pos=-1; entry=c; best=c; entryDt=dt; mfe=0.0

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
                if shortTrail is not None and c>=shortTrail:
                    pnl=entry-c; trades.append((pos,entry,c,pnl,"trail",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
                elif h>=entry+slPts:
                    fill=entry+slPts; pnl=entry-fill; trades.append((pos,entry,fill,pnl,"SL",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
            elif pos>0:
                if longTrail is not None and c<=longTrail:
                    pnl=c-entry; trades.append((pos,entry,c,pnl,"trail",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
                elif l<=entry-slPts:
                    fill=entry-slPts; pnl=fill-entry; trades.append((pos,entry,fill,pnl,"SL",entryDt,mfe)); pos=0;entry=None;best=None;cd=cool
    return trades

if __name__=="__main__":
    print("loading...")
    bars=m.load(); bands=m.vwap_bands(bars)
    years=[2021,2022,2023,2024,2025,2026]
    base=dict(m.P, slPts=70.0, trailArm=40.0, trailGap=40.0)

    print("MIRROR SHORT only, sweep revShortSlope (SL70 trail40/40):")
    print(f"{'rev':>4} | {'pnl0':>7} {'pnl1':>7} {'n':>5} {'pf':>5} {'win':>5} | +yr | per-year(1pt)")
    for rv in (2,4,6,8):
        p=dict(base, enableLong=False, enableShort=True, revShortSlope=float(rv))
        trs=run_variant(bars,bands,p)
        pnl0,n,pf,win,yl0,pos0=m.summ(trs,0.0,years)
        pnl1,_,_,_,yl1,pos1=m.summ(trs,1.0,years)
        print(f'{rv:>4} | {pnl0:>7} {pnl1:>7} {n:>5} {pf:>5} {win:>5} | {pos1}/6 | {yl1}')

    print()
    print("LONG(rev4) + MIRROR SHORT(rev4) combined, SL70 trail40/40:")
    p=dict(base, enableLong=True, enableShort=True, revSlope=4.0, revShortSlope=4.0)
    trs=run_variant(bars,bands,p)
    longs=[t for t in trs if t[0]>0]; shorts=[t for t in trs if t[0]<0]
    for label,sub in (("ALL",trs),("LONG",longs),("SHORT",shorts)):
        pnl0,n,pf,win,yl0,pos0=m.summ(sub,0.0,years)
        pnl1,_,_,_,yl1,pos1=m.summ(sub,1.0,years)
        print(f'{label:6} 0slip {pnl0:>7} 1slip {pnl1:>7} n {n:>5} pf {pf:>5} win {win:>5} +yr {pos1}/6 {yl1}')
    print(" exit mix:", dict(Counter(t[4] for t in trs)))
