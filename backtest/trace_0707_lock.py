import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
PULLBACK = 150.0
REENTRY = 0.7

rows = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
closes = [float(r['close']) for r in rows]
highs = [float(r['high']) for r in rows]
lows = [float(r['low']) for r in rows]
times = [datetime.fromisoformat(r['time']) for r in rows]
n = len(rows)

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

def L(i):
    return times[i].astimezone(LDN).strftime('%a %d-%b %H:%M')

state = 0; sdir = 0; ext = None; spx = None
lock = 0; lockExt = None; lockTrv = None
anchor = None; startBar = None; winN = None

for i in range(n):
    t = times[i]; h = highs[i]; l = lows[i]; c = closes[i]
    if lock != 0 and lockExt is not None:
        need = REENTRY*lockTrv
        if lock < 0 and h >= lockExt+need:
            print("%s  DN-lock CLEARS (high %.0f >= lockLow %.0f + %.0f need)" % (L(i), h, lockExt, need))
            lock = 0
        elif lock > 0 and l <= lockExt-need:
            print("%s  UP-lock CLEARS" % L(i))
            lock = 0
    if state == 0:
        dN = dR = dS = None
        N = WINMIN
        while N <= WINMAX:
            if i >= N-1:
                s, r2 = ols(i, N)
                if s is not None and abs(s)*(N-1) >= RUNMIN and r2 >= MINR2:
                    d = 1 if s > 0 else -1
                    if d != lock and (dN is None or r2 > dR):
                        dN = N; dR = r2; dS = s
            N += WINSTEP
        if dN is not None:
            state = 1; sdir = 1 if dS > 0 else -1
            anchor = i-(dN-1); spx = closes[i-(dN-1)]
            ext = h if sdir > 0 else l; startBar = i; winN = dN
    else:
        ext = max(ext, h) if sdir > 0 else min(ext, l)
        broke = (sdir > 0 and c < ext-PULLBACK) or (sdir < 0 and c > ext+PULLBACK)
        if broke:
            lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
            need = REENTRY*lockTrv
            reclaim = ext + need if sdir < 0 else ext - need
            print("%s  BREAK %s  trend spx=%.0f -> ext=%.0f (travel=%.0f)  => arms %s-lock, needs price to %s %.0f to clear" % (
                L(i), "DN" if sdir < 0 else "UP", spx, ext, abs(ext-spx),
                "DN" if sdir < 0 else "UP",
                "rise to" if sdir < 0 else "fall to", reclaim))
            state = 0; ext = None

    d = times[i].astimezone(LDN).strftime('%d-%b')
    m = times[i].astimezone(LDN).hour*60 + times[i].astimezone(LDN).minute
    if d == '07-Jul' and 8*60 <= m <= 16*60 and lock != 0 and lockExt is not None:
        if m % 30 == 0:
            print("    ... %s still %s-locked; needs %s %.0f, current low=%.0f high=%.0f" % (
                L(i), "DN" if lock < 0 else "UP",
                "rise>=" if lock < 0 else "fall<=", lockExt + REENTRY*lockTrv if lock < 0 else lockExt - REENTRY*lockTrv,
                l, h))
