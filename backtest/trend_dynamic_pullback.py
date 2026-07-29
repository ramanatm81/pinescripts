import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
CT = timezone(timedelta(hours=-5))
WINMIN, WINMAX, WINSTEP = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
BASE_PB = 150.0
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

def run(frac):
    state = 0; sdir = 0; ext = None; spx = None
    lock = 0; lockExt = None; lockTrv = None
    startBar = None; winN = None
    trends = []
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
                spx = closes[i-(dN-1)]
                ext = h if sdir > 0 else l; startBar = i; winN = dN
        else:
            ext = max(ext, h) if sdir > 0 else min(ext, l)
            travel = abs(ext - spx)
            pb = max(BASE_PB, travel*frac) if frac > 0 else BASE_PB
            broke = (sdir > 0 and c < ext-pb) or (sdir < 0 and c > ext+pb)
            if broke:
                trends.append((sdir, times[startBar], spx, times[i], i-startBar, abs(ext-spx), ext, winN, pb))
                lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
                state = 0; ext = None
    return trends

def in_ny(dt):
    ct = dt.astimezone(CT); m = ct.hour*60 + ct.minute
    return 510 <= m <= 569

def summary(trends, label):
    kept = [t for t in trends if not in_ny(t[1])]
    tot = sum(t[5] for t in kept)
    big = sum(1 for t in kept if t[5] >= 400)
    print("%-28s | trends=%3d kept | total travel=%6.0f | avg=%5.0f | >=400pt: %d" % (
        label, len(kept), tot, tot/len(kept) if kept else 0, big))

def show_0707(trends, label):
    print("  %s -- trends touching Tue 07-Jul:" % label)
    for t in trends:
        d, st, spx, bt, bars, tv, ext, wN, pb = t
        s = st.astimezone(LDN); e = bt.astimezone(LDN)
        if s.strftime('%d-%b') == '07-Jul' or e.strftime('%d-%b') == '07-Jul':
            print("    %s %-17s -> %-17s spx=%.0f ext=%.0f travel=%.0f pb@break=%.0f" % (
                "UP" if d > 0 else "DN", s.strftime('%a %d-%b %H:%M'), e.strftime('%a %d-%b %H:%M'),
                spx, ext, tv, pb))
    print()

print("Dynamic pullback = max(150, travel*frac), ratchet. OOS. Baseline frac=0 is static 150.")
print()
for frac in (0.0, 0.3, 0.5, 0.7, 1.0):
    summary(run(frac), "frac=%.1f" % frac)
print()
for frac in (0.0, 0.5, 1.0):
    show_0707(run(frac), "frac=%.1f" % frac)
