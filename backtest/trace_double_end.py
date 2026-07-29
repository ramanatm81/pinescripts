import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
BASE_PB = 150.0
PB_FRAC = 0.5
REENTRY = 0.7
CONFIRM_MIN = 10
CONFIRM_ADV = 40.0
CANCEL_COOL = 20

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
    return times[i].astimezone(LDN).strftime('%H:%M')

state = 0; sdir = 0; ext = None; spx = None
lock = 0; lockExt = None; lockTrv = None
cancelDir = 0; cancelBar = None
dotBar = None; dotPrice = None

for i in range(n):
    h = highs[i]; l = lows[i]; c = closes[i]
    events = []
    if lock != 0 and lockExt is not None:
        need = REENTRY*lockTrv
        if lock < 0 and h >= lockExt+need: lock = 0
        elif lock > 0 and l <= lockExt-need: lock = 0
    if cancelDir != 0 and (cancelBar is None or i - cancelBar >= CANCEL_COOL):
        cancelDir = 0
    if state == 0:
        dN = dR = dS = None
        N = WINMIN
        while N <= WINMAX:
            if i >= N-1:
                s, r2 = ols(i, N)
                if s is not None and abs(s)*(N-1) >= RUNMIN and r2 >= MINR2:
                    d = 1 if s > 0 else -1
                    if d != lock and d != cancelDir and (dN is None or r2 > dR):
                        dN = N; dR = r2; dS = s
            N += WINSTEP
        if dN is not None:
            state = 1; sdir = 1 if dS > 0 else -1
            spx = closes[i-(dN-1)]; ext = h if sdir > 0 else l
            dotBar = i; dotPrice = c
            events.append("START %s N=%d" % ("UP" if sdir > 0 else "DN", dN))
    if state == 1:
        ext = max(ext, h) if sdir > 0 else min(ext, l)
        inConfirm = (i - dotBar) <= CONFIRM_MIN
        adverse = (dotPrice - l) if sdir > 0 else (h - dotPrice)
        cancelLatch = inConfirm and adverse >= CONFIRM_ADV
        travel = abs(ext - spx)
        pb = max(BASE_PB, travel*PB_FRAC)
        broke = (sdir > 0 and c < ext-pb) or (sdir < 0 and c > ext+pb)
        if cancelLatch:
            events.append("END(cancel) %s travel=%.0f" % ("UP" if sdir > 0 else "DN", travel))
            cancelDir = sdir; cancelBar = i
            state = 0; ext = None
        elif broke:
            events.append("END(break) %s travel=%.0f" % ("UP" if sdir > 0 else "DN", travel))
            lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
            state = 0; ext = None
    t = times[i].astimezone(LDN)
    if t.strftime('%d-%b') == '10-Jul' and 15*60+25 <= t.hour*60+t.minute <= 15*60+40:
        estr = ' | '.join(events) if events else ''
        end_count = sum(1 for e in events if e.startswith('END'))
        flag = '  <<<< DOUBLE END BAR' if end_count >= 2 else ''
        print("%s c=%.0f state=%d %s%s" % (t.strftime('%H:%M'), c, state, estr, flag))
