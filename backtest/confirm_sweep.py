import csv, statistics as st
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WS = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
BASE_PB, FRAC = 150.0, 0.5
RE = 0.7
COOL = 5

rows = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
closes = [float(r['close']) for r in rows]
highs = [float(r['high']) for r in rows]
lows = [float(r['low']) for r in rows]
times = [datetime.fromisoformat(r['time']) for r in rows]
n = len(rows)

def ols(e, N):
    if e-N+1 < 0:
        return None, None
    yR = closes[e-(N-1)]
    sx = sy = sxx = syy = sxy = 0.0
    for i in range(N):
        x = float(N-1-i); y = closes[e-i]-yR
        sx += x; sy += y; sxx += x*x; syy += y*y; sxy += x*y
    fN = float(N)
    vX = sxx-sx*sx/fN; vY = syy-sy*sy/fN; cXY = sxy-sx*sy/fN
    return (cXY/vX, (cXY*cXY)/(vX*vY)) if vX > 0 and vY > 0 else (None, None)

def run(CMIN, CADV):
    st_ = 0; sd = 0; ext = None; spx = None
    lk = 0; lex = None; ltr = None
    cd = 0; cb = None; db = None; dp = None
    trends = []
    for i in range(n):
        h = highs[i]; l = lows[i]; c = closes[i]
        if lk != 0 and lex is not None:
            nd = RE*ltr
            if lk < 0 and h >= lex+nd: lk = 0
            elif lk > 0 and l <= lex-nd: lk = 0
        if cd != 0 and (cb is None or i-cb >= COOL):
            cd = 0
        if st_ == 0:
            dN = dR = dS = None; N = WINMIN
            while N <= WINMAX:
                if i >= N-1:
                    s, r2 = ols(i, N)
                    if s is not None and abs(s)*(N-1) >= RUNMIN and r2 >= MINR2:
                        d = 1 if s > 0 else -1
                        if d != lk and d != cd and (dN is None or r2 > dR):
                            dN = N; dR = r2; dS = s
                N += WS
            if dN is not None:
                st_ = 1; sd = 1 if dS > 0 else -1
                spx = closes[i-(dN-1)]; ext = h if sd > 0 else l; db = i; dp = c
        if st_ == 1:
            ext = max(ext, h) if sd > 0 else min(ext, l)
            age = i - db
            inc = (CMIN > 0 and age >= 1 and age <= CMIN)
            adv = (dp - l) if sd > 0 else (h - dp)
            canc = inc and adv >= CADV
            tv = abs(ext - spx); pb = max(BASE_PB, tv*FRAC)
            brk = (sd > 0 and c < ext-pb) or (sd < 0 and c > ext+pb)
            if canc:
                trends.append((sd, age, tv, 'C')); cd = sd; cb = i; st_ = 0; ext = None
            elif brk:
                trends.append((sd, age, abs(ext-spx), 'B')); lk = sd; lex = ext; ltr = max(abs(ext-spx), 1.0); st_ = 0; ext = None
    return trends

def stats(tr, cmin, cadv):
    lives = [x[1] for x in tr]
    trav = [x[2] for x in tr]
    cancels = sum(1 for x in tr if x[3] == 'C')
    surv = [x for x in tr if x[1] > cmin]
    surv_life = [x[1] for x in surv] or [0]
    surv_trav = [x[2] for x in surv] or [0]
    big = sum(1 for x in tr if x[2] >= 400)
    fat = sorted(trav, reverse=True)[:3]
    print("cMin=%2d adv=%2d | trends=%3d cancels=%3d | ALL life med=%4.0f mean=%4.0f | SURVIVORS n=%3d life med=%4.0f mean=%4.0f trav med=%3.0f | >=400pt:%2d | top3 trav=%s" % (
        cmin, cadv, len(tr), cancels,
        st.median(lives), st.mean(lives),
        len(surv), st.median(surv_life), st.mean(surv_life), st.median(surv_trav),
        big, [int(x) for x in fat]))

print("Confirm-window sweep (cancelCool=5, pullbackFrac=0.5). PORT approx -- anchor to 20/40 vs export.")
print("SURVIVORS = trends that outlived the confirm window (life > cMin) = real trends, not cancels.")
print()
print("baseline no-confirm:")
stats(run(0, 999), 0, 999)
print()
for cmin in (5, 10, 15, 20, 30):
    for cadv in (30, 40, 50, 60):
        stats(run(cmin, cadv), cmin, cadv)
    print()
