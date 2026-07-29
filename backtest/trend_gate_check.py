"""
For each fired trend (real dots from export), show winning-window path_ratio next to
its travel, and mark KEEP/KILL under a maxPathRatio gate. Confirms whether a 3.0 gate
preserves the runner trends (#6, #11) while removing chop.
"""
import csv
from datetime import datetime, timezone, timedelta

CT = timezone(timedelta(hours=-5))
LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
GATE = 3.0

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

def win(end):
    best=None; N=WINMIN
    while N<=WINMAX:
        if end>=N-1:
            s,r2=ols(end,N)
            if s is not None and abs(s)*(N-1)>=RUNMIN and r2>=MINR2:
                if best is None or r2>best[2]: best=(N,s,r2)
        N+=WINSTEP
    return best

def pratio(end, N):
    seg=closes[end-(N-1):end+1]
    net=abs(seg[-1]-seg[0])
    total=sum(abs(seg[i+1]-seg[i]) for i in range(len(seg)-1))
    return total/net if net>0 else 999

evstarts=[(i,int(num(r,'EVT_start_dir'))) for i,r in enumerate(rows) if num(r,'EVT_start_dir') is not None]

n=0
print("%2s %3s %-18s %5s %4s %9s %7s %6s" % ("#","dir","START (London)","N","R2","path_rat","travel","gate"))
print("-"*64)
for (i,d) in evstarts:
    ct=times[i].astimezone(CT)
    if 510<=ct.hour*60+ct.minute<=569:
        continue
    n+=1
    w=win(i)
    s=times[i].astimezone(LDN)
    if w is None:
        print("%2d %3s %-18s  no-window" % (n,"UP" if d>0 else "DN",s.strftime('%a %d-%b %H:%M')))
        continue
    N,slope,r2=w
    pr=pratio(i,N)
    ev_travel=None
    tag="KEEP" if pr<=GATE else "KILL"
    print("%2d %3s %-18s %5d %4.2f %9.2f %7s %6s" % (
        n,"UP" if d>0 else "DN",s.strftime('%a %d-%b %H:%M'),N,r2,pr,"",tag))
print()
print("gate = path_ratio <= %.1f" % GATE)
