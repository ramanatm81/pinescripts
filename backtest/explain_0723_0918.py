import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
closes = [float(x['close']) for x in r]
times = [datetime.fromisoformat(x['time']).astimezone(LDN) for x in r]

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

WINMIN, WINMAX, WS = 60, 240, 10
RUNMIN, MINR2 = 150.0, 0.75

def ols(end, N):
    if end - N + 1 < 0:
        return None, None
    yR = closes[end-(N-1)]
    sx = sy = sxx = syy = sxy = 0.0
    for i in range(N):
        x = float(N-1-i); y = closes[end-i]-yR
        sx += x; sy += y; sxx += x*x; syy += y*y; sxy += x*y
    fN = float(N)
    vX = sxx-sx*sx/fN; vY = syy-sy*sy/fN; cXY = sxy-sx*sy/fN
    if vX > 0 and vY > 0:
        return cXY/vX, (cXY*cXY)/(vX*vY)
    return None, None

di = None
for i, t in enumerate(times):
    if t.strftime('%d-%b') == '23-Jul' and t.hour == 9 and t.minute == 18:
        di = i
        break

print('=== bars 23-Jul 08:15 -> 09:30 (where the short signal appeared) ===')
for i, t in enumerate(times):
    if t.strftime('%d-%b') == '23-Jul' and 8*60+15 <= t.hour*60+t.minute <= 9*60+30:
        row = r[i]
        ev = []
        for cn in ('long entry', 'short entry', 'exit'):
            if nz(row.get(cn, '')):
                ev.append(cn)
        wn = (row.get('live win N', '') or '').strip()
        print(t.strftime('%H:%M'), 'C=' + row['close'], 'live=' + (row.get('live (1/0)', '') or '-'), 'N=' + (wn or '-'), ' '.join(ev))

print()
print('=== what the OLS scan saw AT the short-entry bar (23-Jul 09:17, dot bar) ===')
# entry fills at 09:18 open, so the dot/latch was 09:17
db = None
for i, t in enumerate(times):
    if t.strftime('%d-%b') == '23-Jul' and t.hour == 9 and t.minute == 17:
        db = i
        break
if db:
    print('dot bar 09:17 close=%.2f' % closes[db])
    print('%3s %8s %8s %s' % ('N', 'slope', 'r2', 'qualifies?'))
    best = None
    for N in range(WINMIN, WINMAX + 1, WS):
        s, r2 = ols(db, N)
        if s is not None:
            run = abs(s)*(N-1)
            q = run >= RUNMIN and r2 >= MINR2
            if q or run >= 100:
                d = 'DOWN' if s < 0 else 'UP'
                print('%3d %8.3f %8.3f  run=%.0f %s %s' % (N, s, r2, run, d, 'QUALIFIES' if q else ''))
            if q and (best is None or r2 > best[2]):
                best = (N, s, r2)
    if best:
        print('WINNER: N=%d slope=%.3f (%s) r2=%.3f' % (best[0], best[1], 'DOWN' if best[1] < 0 else 'UP', best[2]))
    print()
    print('price N bars ago vs now (is the WINDOW net down even if recent bars are up?):')
    for N in (60, 100, best[0] if best else 100):
        print('  N=%3d: %.2f (%s) -> %.2f (now)  net %.1f' % (
            N, closes[db-(N-1)], times[db-(N-1)].strftime('%H:%M'), closes[db], closes[db]-closes[db-(N-1)]))
