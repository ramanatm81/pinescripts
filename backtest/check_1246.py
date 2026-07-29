import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

p = {c.replace('P_', ''): r[600][c].strip() for c in r[0].keys() if c.startswith('P_')}
print('STALE PARAMS:', {k: p.get(k) for k in ('enableStale', 'staleBars', 'staleFavPts')})
print()

rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, row))

# find the short entry at/near 12-Jul 23:46
di = None
for i, (t, row) in enumerate(rows):
    if t.strftime('%d-%b') == '12-Jul' and t.hour == 23 and 44 <= t.minute <= 48 and nz(row.get('short entry', '')):
        di = i
        break
if di is None:
    print('no short entry found near 12-Jul 23:46; scanning wider...')
    for i, (t, row) in enumerate(rows):
        if t.strftime('%d-%b') == '12-Jul' and t.hour == 23 and nz(row.get('short entry', '')):
            print('  short entry at', t.strftime('%H:%M'))
else:
    dot = float(rows[di][1]['close'])
    print('SHORT dot at %s, dotClose=%.2f (fill next bar)' % (rows[di][0].strftime('%H:%M'), dot))
    print('stale: at age = staleBars, if favTravel(dot-extreme low) < staleFavPts -> cancel')
    print()
    ext = float(rows[di][1]['low'])
    STALE = int(float(p.get('staleBars', 10)))
    FAV = float(p.get('staleFavPts', 10))
    print('%3s %6s %9s %9s %9s %7s %s' % ('age', 'time', 'high', 'low', 'ext(low)', 'favTrav', 'note'))
    for k in range(0, STALE + 5):
        t, row = rows[di + k]
        l = float(row['low']); h = float(row['high'])
        ext = min(ext, l)
        fav = dot - ext
        note = ''
        if k == STALE:
            note = 'STALE CHECK: fav=%.1f %s %.0f -> %s' % (fav, '<' if fav < FAV else '>=', FAV, 'CANCEL' if fav < FAV else 'survives')
        ev = 'cancel exit' if nz(row.get('cancel exit', '')) else ''
        print('%3d %6s %9.2f %9.2f %9.2f %7.1f %s %s' % (k, t.strftime('%H:%M'), h, l, ext, fav, note, ev))
