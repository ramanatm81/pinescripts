import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
WINMIN, WINMAX, WS = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
BASE_PB, FRAC = 150.0, 0.5
RE = 0.7

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

def L(i):
    return times[i].astimezone(LDN).strftime('%H:%M')

def run(CMIN, CADV, COOL, label):
    st = 0; sd = 0; ext = None; spx = None
    lk = 0; lex = None; ltr = None
    cd = 0; cb = None; db = None; dp = None
    print("=== confirmMins=%d confirmAdvPts=%d cancelCool=%d ===" % (CMIN, CADV, COOL))
    for i in range(n):
        h = highs[i]; l = lows[i]; c = closes[i]
        ev = ""
        if lk != 0 and lex is not None:
            nd = RE*ltr
            if lk < 0 and h >= lex+nd: lk = 0
            elif lk > 0 and l <= lex-nd: lk = 0
        if cd != 0 and (cb is None or i-cb >= COOL):
            cd = 0
        if st == 0:
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
                st = 1; sd = 1 if dS > 0 else -1
                spx = closes[i-(dN-1)]; ext = h if sd > 0 else l; db = i; dp = c
                ev = "LATCH %s N=%d" % ("UP" if sd > 0 else "DN", dN)
            else:
                blocked = ""
                if cd != 0:
                    blocked = " [%s-cooldown blocks re-latch %d more]" % ("UP" if cd > 0 else "DN", COOL-(i-cb))
                if lk != 0:
                    blocked += " [%s-locked]" % ("UP" if lk > 0 else "DN")
                ev = "flat" + blocked
        if st == 1:
            ext = max(ext, h) if sd > 0 else min(ext, l)
            age = i - db
            inc = (age >= 1 and age <= CMIN)
            adv = (dp - l) if sd > 0 else (h - dp)
            canc = inc and adv >= CADV
            tv = abs(ext - spx); pb = max(BASE_PB, tv*FRAC)
            brk = (sd > 0 and c < ext-pb) or (sd < 0 and c > ext+pb)
            if canc:
                ev = "CANCEL %s age=%d adv=%.0f -> cooldown %d bars" % ("UP" if sd > 0 else "DN", age, adv, COOL)
                cd = sd; cb = i; st = 0; ext = None
            elif brk:
                ev = "BREAK %s" % ("UP" if sd > 0 else "DN")
                lk = sd; lex = ext; ltr = max(abs(ext-spx), 1.0); st = 0; ext = None
            else:
                ev = "live %s len=%d" % ("UP" if sd > 0 else "DN", age+1)
        t = times[i].astimezone(LDN)
        if t.strftime('%d-%b') == '09-Jul' and 1*60+10 <= t.hour*60+t.minute <= 1*60+30:
            print("%s c=%.0f L=%.0f | %s" % (L(i), c, l, ev))
    print()

run(10, 30, 5, "10/30")
run(20, 30, 5, "20/30")
