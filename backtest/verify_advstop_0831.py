import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, float(row['open']), float(row['high']), float(row['low']), float(row['close'])))

di = None
for i, (t, o, h, l, c) in enumerate(rows):
    if t.strftime('%d-%b') == '24-Jul' and t.hour == 8 and t.minute == 31:
        di = i
        break

dot = rows[di][4]
direction = 1
ADV_STOP = 40.0
PROVEN = 60.0

liveExtreme = rows[di][2] if direction > 0 else rows[di][3]
print('LONG dot 08:31 dot_close=', dot, ' adverseStop=', ADV_STOP, ' provenPts=', PROVEN)
print('age  time   H       L       favTravel  proven  adverse  STOP?')
for k in range(0, 45):
    t, o, h, l, c = rows[di + k]
    liveExtreme = max(liveExtreme, h) if direction > 0 else min(liveExtreme, l)
    favTravel = (liveExtreme - dot) if direction > 0 else (dot - liveExtreme)
    proven = favTravel >= PROVEN
    adverse = (dot - l) if direction > 0 else (h - dot)
    stop = ADV_STOP > 0 and k >= 1 and (not proven) and adverse >= ADV_STOP
    print('%3d  %s  %.2f  %.2f  %8.2f   %s    %7.2f  %s' % (
        k, t.strftime('%H:%M'), h, l, favTravel, 'Y' if proven else 'n', adverse, 'CANCEL' if stop else ''))
    if stop:
        break
