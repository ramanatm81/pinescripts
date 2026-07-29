import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
CT = timezone(timedelta(hours=-5))
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

def run(confMin=0, confAdv=0):
    state = 0; sdir = 0; ext = None; spx = None
    lock = 0; lockExt = None; lockTrv = None
    startBar = None; winN = None; dotClose = None
    trends = []
    cancelled = []
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
                startBar = i; winN = dN; dotClose = c
        else:
            ext = max(ext, h) if sdir > 0 else min(ext, l)
            if confMin > 0 and (i - startBar) <= confMin:
                adv = (h - dotClose) if sdir < 0 else (dotClose - l)
                if adv >= confAdv:
                    cancelled.append((sdir, times[startBar], spx, i-startBar, adv))
                    state = 0; ext = None
                    continue
            travel = abs(ext - spx)
            pb = max(BASE_PB, travel*PB_FRAC)
            broke = (sdir > 0 and c < ext-pb) or (sdir < 0 and c > ext+pb)
            if broke:
                trends.append((sdir, times[startBar], spx, times[i], i-startBar, abs(ext-spx), ext))
                lock = sdir; lockExt = ext; lockTrv = max(abs(ext-spx), 1.0)
                state = 0; ext = None
    return trends, cancelled

def in_ny(dt):
    ct = dt.astimezone(CT); m = ct.hour*60 + ct.minute
    return 510 <= m <= 569

def summ(trends, cancelled, label):
    kept = [t for t in trends if not in_ny(t[1])]
    tot = sum(t[5] for t in kept)
    big = sum(1 for t in kept if t[5] >= 400)
    canc = [c for c in cancelled if not in_ny(c[1])]
    print("%-22s | trends=%3d | travel=%6.0f | avg=%4.0f | >=400pt:%2d | cancelled:%3d" % (
        label, len(kept), tot, tot/len(kept) if kept else 0, big, len(canc)))
    return kept

print("Confirmation window: cancel a latch if adverse move >= X pts within N min of the dot.")
print("Cancelled latch does NOT arm lock. Dynamic pullback frac=0.5. OOS.")
print()
base_kept = summ(*run(0, 0), label="BASELINE (no confirm)")
base_set = set((t[0], t[1]) for t in base_kept)
print()
for cm in (10, 20, 30):
    for ca in (20, 30, 40):
        kept = summ(*run(cm, ca), label="N=%dmin adv>=%dpt" % (cm, ca))
    print()

print("Check: does confirmation cancel any BIG runner (>=400pt in baseline)?")
big_runners = [t for t in base_kept if t[5] >= 400]
for cm, ca in [(20, 30), (30, 40)]:
    kept, canc = run(cm, ca)
    kept_starts = set((t[0], t[1]) for t in kept)
    lost = [t for t in big_runners if (t[0], t[1]) not in kept_starts]
    print("  N=%dmin adv>=%dpt : lost %d of %d big runners" % (cm, ca, len(lost), len(big_runners)))
    for t in lost:
        print("     LOST %s %s travel=%.0f" % ("UP" if t[0] > 0 else "DN", t[1].astimezone(LDN).strftime('%a %d-%b %H:%M'), t[5]))
