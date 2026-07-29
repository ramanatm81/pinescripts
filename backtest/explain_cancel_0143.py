import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, float(row['open']), float(row['high']), float(row['low']), float(row['close'])))

p = {c.replace('P_', ''): r[600][c].strip() for c in r[0].keys() if c.startswith('P_')}
print('PARAMS:', {k: p[k] for k in ('confirmMins', 'confirmAdvPts', 'adverseStopPts', 'provenPts', 'pullbackPts', 'pullbackFrac')})
print()

di = None
for i, (t, o, h, l, c) in enumerate(rows):
    if t.strftime('%d-%b') == '08-Jul' and t.hour == 1 and t.minute == 42:
        di = i
        break

DIR = 1
DOTPX = rows[di][4]
ADV_STOP = float(p['adverseStopPts'])
PROVEN = float(p['provenPts'])
CMIN = int(float(p['confirmMins']))
CADV = float(p['confirmAdvPts'])

print('LONG dot 08-Jul 01:42, dotClose=%.2f' % DOTPX)
print('adverseStop=%.0f (fires if price drops this far below dot, until proven>=%.0f)' % (ADV_STOP, PROVEN))
print('confirmMins=%d (0=confirm window OFF)' % CMIN)
print()
print('age  time   H       L       favTrav proven adverse(dot-low) STOP?')
ext = rows[di][2]
for k in range(0, 40):
    t, o, h, l, c = rows[di + k]
    ext = max(ext, h)
    fav = ext - DOTPX
    proven = fav >= PROVEN
    adverse = DOTPX - l
    stop = ADV_STOP > 0 and k >= 1 and (not proven) and adverse >= ADV_STOP
    confirm = CMIN > 0 and 1 <= k <= CMIN and adverse >= CADV
    tag = ''
    if stop:
        tag = 'ADVERSE-STOP CANCEL'
    elif confirm:
        tag = 'CONFIRM CANCEL'
    print('age %2d  %s  %.2f  %.2f  %6.1f   %s     %7.2f          %s' % (
        k, t.strftime('%H:%M'), h, l, fav, 'Y' if proven else 'n', adverse, tag))
    if stop or confirm:
        break
