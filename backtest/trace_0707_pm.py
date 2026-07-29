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

state = 0; sdir = 0; ext = None; spx = None
lock = 0; lockExt = None; lockTrv = None
anchor = None; startBar = None; winN = None

lo = LDN
def inwin(t):
    m = t.astimezone(lo).hour*60 + t.astimezone(lo).minute
    d = t.astimezone(lo).strftime('%d-%b')
    return d == '07-Jul' and 8*60+26 <= m <= 15*60+39

print("Tue 07-Jul 08:26-15:39 London. winMin=60 winMax=240 run>=150 R2>=0.75 pullback=150")
print("%-6s %8s %6s | %-28s | %s" % ("LDN", "close", "state", "detect (best qualifying)", "event"))

for i in range(n):
    t = times[i]; h = highs[i]; l = lows[i]; c = closes[i]
    ev = ""
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
            anchor = i-(dN-1); spx = closes[i-(dN-1)]
            ext = h if sdir > 0 else l; startBar = i; winN = dN
            ev = "LATCH %s N=%d r2=%.3f spx=%.0f" % ("UP" if sdir > 0 else "DN", dN, dR, spx)
        detect = ("best N=%d %s r2=%.3f" % (dN, "UP" if dS > 0 else "DN", dR)) if dN else "no qualify"
        if lock != 0:
            detect += " [lock %s]" % ("DN" if lock < 0 else "UP")
    else:
        ext = max(ext, h) if sdir > 0 else min(ext, l)
        broke = (sdir > 0 and c < ext-PULLBACK) or (sdir < 0 and c > ext+PULLBACK)
        detect = "LIVE %s ext=%.0f" % ("UP" if sdir > 0 else "DN", ext)
        if broke:
            ev = "BREAK %s ext=%.0f travel=%.0f" % ("UP" if sdir > 0 else "DN", ext, abs(ext-spx))
            lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
            state = 0; ext = None
    if inwin(t) and (t.astimezone(lo).minute % 3 == 0 or ev):
        print("%-6s %8.0f %6d | %-28s | %s" % (t.astimezone(lo).strftime('%H:%M'), c, state, detect, ev))
