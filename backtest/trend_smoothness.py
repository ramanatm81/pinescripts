"""
Measure how 'smooth' each fired trend actually is, using the real dot times from
the live_trend.pine export. For each START dot we scan winMin..winMax exactly like
the pine, find the winning window (best R2 that clears run>=150 and R2>=0.75), and
report metrics R2 does AND does not capture:

  R2        : the pine's own smoothness gate (scatter around the fit line)
  path_ratio: sum(|bar-to-bar move|) / |net move|. A perfectly straight run = ~1.0.
              A choppy zig-zag that nets the same distance = 2, 3, 4x. R2 can miss this.
  rev_frac  : fraction of bars whose 1-bar change is AGAINST the trend direction.
              0 = never pulls back, 0.5 = coin-flip (chop). R2 can miss this too.
  max_adverse: biggest counter-trend pullback (pts) inside the winning window.

This tells us whether R2>=0.75 alone is keeping trends smooth, or whether chop is
sneaking through that a path-based filter would catch.
"""
import csv
from datetime import datetime, timezone, timedelta

CT = timezone(timedelta(hours=-5))
LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75

rows = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
closes = [float(r['close']) for r in rows]
times = [datetime.fromisoformat(r['time']) for r in rows]

def num(r, k):
    v = r.get(k, '').strip()
    if v in ('', 'NaN'): return None
    try: return float(v)
    except: return None

def ols(end, N):
    yRef = closes[end-(N-1)]
    sx=sy=sxx=syy=sxy=0.0
    for i in range(N):
        x=float(N-1-i); y=closes[end-i]-yRef
        sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y
    fN=float(N)
    vX=sxx-sx*sx/fN; vY=syy-sy*sy/fN; cXY=sxy-sx*sy/fN
    if vX>0 and vY>0:
        return cXY/vX, (cXY*cXY)/(vX*vY)
    return None, None

def winning_window(end):
    best=None
    N=WINMIN
    while N<=WINMAX:
        if end>=N-1:
            s,r2=ols(end,N)
            if s is not None and abs(s)*(N-1)>=RUNMIN and r2>=MINR2:
                if best is None or r2>best[2]:
                    best=(N,s,r2)
        N+=WINSTEP
    return best

def path_metrics(end, N, direction):
    seg=closes[end-(N-1):end+1]
    net=seg[-1]-seg[0]
    total=sum(abs(seg[i+1]-seg[i]) for i in range(len(seg)-1))
    path_ratio = total/abs(net) if net!=0 else 999
    rev=0; max_adv=0.0; run_adv=0.0
    for i in range(len(seg)-1):
        ch=seg[i+1]-seg[i]
        if direction>0:
            if ch<0:
                rev+=1; run_adv+=ch
            else:
                run_adv=0.0
        else:
            if ch>0:
                rev+=1; run_adv+=ch
            else:
                run_adv=0.0
        max_adv=min(max_adv, run_adv) if direction>0 else max_adv
        if direction<0: max_adv=max(max_adv, run_adv)
    rev_frac=rev/(len(seg)-1)
    return path_ratio, rev_frac, abs(max_adv)

starts=[]
for i,r in enumerate(rows):
    sd=num(r,'EVT_start_dir')
    if sd is not None:
        starts.append((i,int(sd)))

print("dot smoothness at latch (winMin=60..240, pickBest R2). path_ratio 1.0=straight, higher=choppier")
print()
hdr="%-19s %3s %4s %6s %9s %8s %10s" % ("START (London)","dir","N","R2","path_rat","rev_frac","max_adv")
print(hdr); print("-"*len(hdr))
allr2=[]; allpr=[]
for (i,d) in starts:
    w=winning_window(i)
    ct=times[i].astimezone(CT)
    if 510<=ct.hour*60+ct.minute<=569:
        continue
    s=times[i].astimezone(LDN)
    if w is None:
        print("%-19s %3s  no-window" % (s.strftime('%a %d-%b %H:%M'), "UP" if d>0 else "DN"))
        continue
    N,slope,r2=w
    pr,rf,ma=path_metrics(i,N,d)
    allr2.append(r2); allpr.append(pr)
    print("%-19s %3s %4d %6.2f %9.2f %8.2f %10.0f" % (
        s.strftime('%a %d-%b %H:%M'), "UP" if d>0 else "DN", N, r2, pr, rf, ma))

if allr2:
    allr2s=sorted(allr2); allprs=sorted(allpr)
    n=len(allr2s)
    print()
    print("R2       : min %.2f  median %.2f  max %.2f" % (allr2s[0], allr2s[n//2], allr2s[-1]))
    print("path_rat : min %.2f  median %.2f  max %.2f  (1.0=perfectly straight)" % (allprs[0], allprs[n//2], allprs[-1]))
