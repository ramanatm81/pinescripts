import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
BASE_PB = 150.0
PB_FRAC = 0.5
REENTRY = 0.7

rows = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
closes = [float(r['close']) for r in rows]
highs = [float(r['high']) for r in rows]
lows = [float(r['low']) for r in rows]
times = [datetime.fromisoformat(r['time']) for r in rows]
n = len(rows)

def nz(v):
    return (v or '').strip() not in ('', 'NaN')

ind_dots = []
for i, r in enumerate(rows):
    if nz(r.get('EVT_start_dir', '')):
        ind_dots.append((i, int(float(r['EVT_start_dir'])), times[i]))

def ols(end, N):
    if end - N + 1 < 0:
        return None, None
    yRef = closes[end-(N-1)]
    sx = sy = sxx = syy = sxy = 0.0
    for i in range(N):
        x = float(N-1-i); y = closes[end-i]-yRef
        sx += x; sy += y; sxx += x*x; syy += y*y; sxy += x*y
    fN = float(N)
    vX = sxx-sx*sx/fN; vY = syy-sy*sy/fN; cXY = sxy-sx*sy/fN
    if vX > 0 and vY > 0:
        return cXY/vX, (cXY*cXY)/(vX*vY)
    return None, None

def port_dots(pickbest=True):
    state = 0; sdir = 0; ext = None; spx = None
    lock = 0; lockExt = None; lockTrv = None
    dots = []
    for i in range(n):
        h = highs[i]; l = lows[i]; c = closes[i]
        if lock != 0 and lockExt is not None:
            need = REENTRY*lockTrv
            if lock < 0 and h >= lockExt+need:
                lock = 0
            elif lock > 0 and l <= lockExt-need:
                lock = 0
        if state == 0:
            dN = dR = dS = None
            N = WINMIN
            while N <= WINMAX:
                if i >= N-1:
                    s, r2 = ols(i, N)
                    if s is not None and abs(s)*(N-1) >= RUNMIN and r2 >= MINR2:
                        d = 1 if s > 0 else -1
                        better = (dN is None) or (pickbest and r2 > dR)
                        if d != lock and better:
                            dN = N; dR = r2; dS = s
                N += WINSTEP
            if dN is not None:
                state = 1; sdir = 1 if dS > 0 else -1
                spx = closes[i-(dN-1)]; ext = h if sdir > 0 else l
                dots.append((i, sdir, times[i], dN))
        else:
            ext = max(ext, h) if sdir > 0 else min(ext, l)
            travel = abs(ext - spx)
            pb = max(BASE_PB, travel*PB_FRAC)
            broke = (sdir > 0 and c < ext-pb) or (sdir < 0 and c > ext+pb)
            if broke:
                lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
                state = 0; ext = None
    return dots

pd = port_dots(True)
print("indicator dots: %d | port dots: %d" % (len(ind_dots), len(pd)))
print()
print("First 15 side by side (LDN time):")
print("%-3s %-22s %-22s" % ("#", "INDICATOR", "PORT"))
for k in range(15):
    a = ind_dots[k] if k < len(ind_dots) else None
    b = pd[k] if k < len(pd) else None
    astr = ("%s dir=%+d" % (a[2].astimezone(LDN).strftime('%a %d-%b %H:%M'), a[1])) if a else "--"
    bstr = ("%s dir=%+d N=%d" % (b[2].astimezone(LDN).strftime('%a %d-%b %H:%M'), b[1], b[3])) if b else "--"
    mark = "" if (a and b and a[0] == b[0]) else "  <-- MISMATCH"
    print("%-3d %-22s %-22s%s" % (k+1, astr, bstr, mark))
