import csv, statistics as st, os
from datetime import datetime, timezone, timedelta

WINMIN, WINMAX, WS = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
BASE_PB, FRAC = 150.0, 0.5
RE = 0.7
CMIN, CADV, COOL = 20, 40.0, 5

def load(path, five_yr):
    opens = []; closes = []; highs = []; lows = []; dts = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            t = row['time']
            if not t:
                continue
            try:
                o = float(row['open']); h = float(row['high']); l = float(row['low']); c = float(row['close'])
            except (ValueError, KeyError):
                continue
            dt = datetime.fromisoformat(t)
            opens.append(o); closes.append(c); highs.append(h); lows.append(l); dts.append(dt)
    return opens, closes, highs, lows, dts

def ols(closes, e, N):
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

def run(opens, closes, highs, lows, dts=None):
    o_arr = opens
    n = len(closes)
    ROLL_JUMP = 80.0   # a contract roll shows up as a large open-vs-prev-close jump
    # Precompute boundary bars ONCE (outside the hot loop): a live trend must END at the
    # CONTRACT boundary -- a big time gap (session/holiday break) OR a big price jump (the
    # roll itself, incl. the 13 continuous-time midnight-UTC quarterly rolls). No fixed cap.
    boundary = [False]*n
    for i in range(1, n):
        tg = dts is not None and (dts[i]-dts[i-1]).total_seconds() > 600
        pj = abs(o_arr[i] - closes[i-1]) > ROLL_JUMP
        if tg or pj:
            boundary[i] = True
    st_ = 0; sd = 0; ext = None; spx = None
    lk = 0; lex = None; ltr = None
    cd = 0; cb = None; db = None; dp = None
    trends = []
    for i in range(n):
        h = highs[i]; l = lows[i]; c = closes[i]
        if st_ == 1 and db is not None and boundary[i]:
            trends.append((sd, i-db, abs(ext-spx), 'X'))
            st_ = 0; ext = None
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
                    s, r2 = ols(closes, i, N)
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
            inc = (age >= 1 and age <= CMIN)
            adv = (dp - l) if sd > 0 else (h - dp)
            canc = inc and adv >= CADV
            tv = abs(ext - spx); pb = max(BASE_PB, tv*FRAC)
            brk = (sd > 0 and c < ext-pb) or (sd < 0 and c > ext+pb)
            if canc:
                trends.append((sd, age, tv, 'C')); cd = sd; cb = i; st_ = 0; ext = None
            elif brk:
                trends.append((sd, age, abs(ext-spx), 'B')); lk = sd; lex = ext; ltr = max(abs(ext-spx), 1.0); st_ = 0; ext = None
    return trends

def pct(v, p):
    v = sorted(v); k = (len(v)-1)*p/100; f0 = int(k)
    return v[f0] if f0+1 >= len(v) else v[f0]+(v[f0+1]-v[f0])*(k-f0)

def dist(sub, lbl):
    if not sub:
        print(lbl+': none'); return
    L = [x[1] for x in sub]; T = [x[2] for x in sub]
    print("%-16s n=%4d | life bars p25=%4.0f MED=%4.0f p75=%5.0f max=%5.0f mean=%4.0f | MEDh=%4.1f maxh=%5.1f | trav MED=%4.0f max=%4.0f" % (
        lbl, len(sub), pct(L, 25), st.median(L), pct(L, 75), max(L), st.mean(L),
        st.median(L)/60, max(L)/60, st.median(T), max(T)))

def report(path, tag):
    opens, closes, highs, lows, dts = load(path, tag == '5YR')
    tr = run(opens, closes, highs, lows, dts)
    surv = [x for x in tr if x[1] > CMIN]
    canc = [x for x in tr if x[1] <= CMIN]
    print("######## %s : %s ########" % (tag, os.path.basename(path)))
    print("bars=%d  paired trends=%d  survivors=%d  cancelled=%d" % (len(closes), len(tr), len(surv), len(canc)))
    print("params: confirmMins=%d confirmAdvPts=%.0f cancelCool=%d pullbackFrac=%.1f" % (CMIN, CADV, COOL, FRAC))
    print("-- SURVIVORS (real trends) --")
    dist(surv, 'ALL surv')
    dist([x for x in surv if x[0] > 0], 'UP surv')
    dist([x for x in surv if x[0] < 0], 'DN surv')
    rollclose = sum(1 for x in tr if x[3] == 'X')
    print("roll/gap force-closes: %d" % rollclose)
    print("-- CANCELLED (false latches) --")
    dist(canc, 'ALL canc')
    big = sum(1 for x in tr if x[2] >= 400)
    top = sorted((x[2] for x in tr), reverse=True)[:5]
    print("fat tail: >=400pt trends=%d  top5 travel=%s" % (big, [int(x) for x in top]))
    print()

if __name__ == '__main__':
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else 'both'
    if which in ('oos', 'both'):
        report('/Users/maheshk81/Downloads/data.csv', 'OOS-PORT (anchor vs your export)')
    if which in ('5yr', 'both'):
        report('/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv', '5YR')
