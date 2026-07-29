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
startBar = None

print("Original logic + pullbackFrac=0.5. Raw best-qualifying window each bar, 06-Jul 18:35-19:10 London.")
print("(this replays the WHOLE series so lock state is correct at 18:xx)")
print()

for i in range(n):
    t = times[i]; h = highs[i]; l = lows[i]; c = closes[i]
    if lock != 0 and lockExt is not None:
        need = REENTRY*lockTrv
        if lock < 0 and h >= lockExt+need:
            lock = 0
        elif lock > 0 and l <= lockExt-need:
            lock = 0

    ev = ""
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
            spx = closes[i-(dN-1)]; ext = h if sdir > 0 else l; startBar = i
            ev = "*** LATCH %s winN=%d r2=%.3f anchor=%s startPx=%.0f ***" % (
                "UP" if sdir > 0 else "DN", dN, dR, L(i-(dN-1)), spx)
        detect = ("qual: best N=%d %s r2=%.3f" % (dN, "UP" if dS > 0 else "DN", dR)) if dN else "no qualify"
        if lock != 0 and not dN:
            detect += " [%s-locked]" % ("DN" if lock < 0 else "UP")
    else:
        ext = max(ext, h) if sdir > 0 else min(ext, l)
        travel = abs(ext - spx)
        pb = max(BASE_PB, travel*PB_FRAC)
        broke = (sdir > 0 and c < ext-pb) or (sdir < 0 and c > ext+pb)
        detect = "LIVE %s ext=%.0f travel=%.0f" % ("UP" if sdir > 0 else "DN", ext, travel)
        if broke:
            ev = "*** BREAK %s ext=%.0f travel=%.0f pb=%.0f ***" % ("UP" if sdir > 0 else "DN", ext, abs(ext-spx), pb)
            lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
            state = 0; ext = None

    ld = times[i].astimezone(LDN)
    if ld.strftime('%d-%b') == '06-Jul' and 18*60+35 <= ld.hour*60+ld.minute <= 19*60+10:
        print("%s c=%.0f H=%.0f L=%.0f | %-32s %s" % (ld.strftime('%H:%M'), c, h, l, detect, ev))
