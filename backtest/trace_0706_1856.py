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
startBar = None; winN = None

for i in range(n):
    t = times[i]; h = highs[i]; l = lows[i]; c = closes[i]
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
                    if d != lock and (dN is None or r2 > dR):
                        dN = N; dR = r2; dS = s
            N += WINSTEP
        if dN is not None:
            state = 1; sdir = 1 if dS > 0 else -1
            spx = closes[i-(dN-1)]; ext = h if sdir > 0 else l
            startBar = i; winN = dN
            ld = times[i].astimezone(LDN)
            if ld.strftime('%d-%b') == '06-Jul' and 18*60+40 <= ld.hour*60+ld.minute <= 19*60+30:
                print("LATCH %s at %s: winN=%d r2=%.3f startPx=%.0f dotClose=%.0f dotHigh=%.0f dotLow=%.0f" % (
                    "UP" if sdir > 0 else "DN", L(i), dN, dR, spx, c, h, l))
                for k in range(i, min(i+35, n)):
                    tk = times[k].astimezone(LDN)
                    fav = (lows[k]-spx) if sdir < 0 else (highs[k]-spx)
                    adv = (highs[k]-closes[i]) if sdir < 0 else (closes[i]-lows[k])
                    mark = " <-- reverses UP" if (sdir < 0 and highs[k] > c) else (" <-- reverses DN" if (sdir > 0 and lows[k] < c) else "")
                    print("   +%2dmin %s close=%.0f H=%.0f L=%.0f  favMove=%+.0f advMove=%+.0f%s" % (
                        k-i, tk.strftime('%H:%M'), closes[k], highs[k], lows[k], fav if sdir < 0 else fav, adv, mark))
    else:
        ext = max(ext, h) if sdir > 0 else min(ext, l)
        travel = abs(ext - spx)
        pb = max(BASE_PB, travel*PB_FRAC)
        broke = (sdir > 0 and c < ext-pb) or (sdir < 0 and c > ext+pb)
        if broke:
            ld = times[startBar].astimezone(LDN)
            if ld.strftime('%d-%b') == '06-Jul' and 18*60+40 <= ld.hour*60+ld.minute <= 19*60+30:
                print("   BREAK at %s: ext=%.0f travel=%.0f pb=%.0f" % (L(i), ext, abs(ext-spx), pb))
            lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
            state = 0; ext = None
