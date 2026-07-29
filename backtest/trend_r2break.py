"""
Test the user's idea: after a trend latches, break it when the anchor->now R2
falls below a threshold (REPLACING the 300pt pullback rule). Measure on OOS.

Detection is identical to live_trend.pine (winMin=60..240, run>=150, R2>=0.75,
pickBest). Once latched, each bar refit OLS over anchor..now; if that R2 < r2Break,
end the trend HERE. Compare travel/duration vs the pullback-rule baseline.

Reports each trend under the R2-break rule and, for the two runners (#6 #11) and
the dud (#13), what happens.
"""
import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
CT = timezone(timedelta(hours=-5))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
PULLBACK = 300.0
REENTRY = 0.7

rows = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
closes = [float(r['close']) for r in rows]
highs = [float(r['high']) for r in rows]
lows = [float(r['low']) for r in rows]
times = [datetime.fromisoformat(r['time']) for r in rows]
n = len(rows)

def ols(end, N):
    yRef = closes[end-(N-1)]
    sx=sy=sxx=syy=sxy=0.0
    for i in range(N):
        x=float(N-1-i); y=closes[end-i]-yRef
        sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y
    fN=float(N)
    vX=sxx-sx*sx/fN; vY=syy-sy*sy/fN; cXY=sxy-sx*sy/fN
    if vX>0 and vY>0: return cXY/vX,(cXY*cXY)/(vX*vY)
    return None,None

def run(mode, r2break=0.75, cap=1500):
    """mode 'pullback' or 'r2break'. Returns list of trends."""
    state=0; anchor=None; sdir=0; ext=None; spx=None; lock=0; lockExt=None; lockTrv=None
    startBar=None
    trends=[]
    for i in range(n):
        h=highs[i]; l=lows[i]; c=closes[i]
        if lock!=0 and lockExt is not None:
            need=REENTRY*lockTrv
            if lock<0 and h>=lockExt+need: lock=0
            elif lock>0 and l<=lockExt-need: lock=0
        if state==0:
            dN=None;dR=None;dS=None
            N=WINMIN
            while N<=WINMAX:
                if i>=N-1:
                    s,r2=ols(i,N)
                    if s is not None and abs(s)*(N-1)>=RUNMIN and r2>=MINR2:
                        d=1 if s>0 else -1
                        if d!=lock and (dN is None or r2>dR): dN=N;dR=r2;dS=s
                N+=WINSTEP
            if dN is not None:
                state=1; sdir=1 if dS>0 else -1
                anchor=i-(dN-1); spx=closes[i-(dN-1)]
                ext=h if sdir>0 else l; startBar=i
        else:
            ext=max(ext,h) if sdir>0 else min(ext,l)
            liveN=min(i-anchor+1, cap)
            broke=False
            if mode=='pullback':
                broke=(sdir>0 and c<ext-PULLBACK) or (sdir<0 and c>ext+PULLBACK)
            else:
                s,r2=ols(i, liveN)
                broke = (r2 is None) or (r2 < r2break)
            if broke:
                travel=abs(ext-spx)
                trends.append((sdir, times[startBar], spx, times[i], i-startBar, travel, ext))
                lock=sdir; lockExt=ext; lockTrv=max(abs(ext-spx),1.0)
                state=0; ext=None
    return trends

def in_ny(dt):
    ct=dt.astimezone(CT); m=ct.hour*60+ct.minute
    return 510<=m<=569

def show(trends, label):
    kept=[t for t in trends if not in_ny(t[1])]
    print("=== %s === (%d trends, %d kept after NY-open excl)" % (label, len(trends), len(kept)))
    print("%2s %3s %-18s %-18s %7s %6s" % ("#","dir","START","END","travel","bars"))
    tot=0
    for i,t in enumerate(kept,1):
        d,st,spx,bt,bars,tv,ext=t
        tot+=tv
        print("%2d %3s %-18s %-18s %7.0f %6d" % (i,"UP" if d>0 else "DN",
            st.astimezone(LDN).strftime('%a %d-%b %H:%M'),
            bt.astimezone(LDN).strftime('%a %d-%b %H:%M'), tv, bars))
    print("total travel: %.0f pt  | trend count: %d  | avg travel: %.0f" % (tot,len(kept),tot/len(kept) if kept else 0))
    print()

show(run('pullback'), "BASELINE pullback 300pt")
for thr in (0.75, 0.85, 0.90):
    show(run('r2break', r2break=thr), "R2-break < %.2f (replaces pullback)" % thr)
