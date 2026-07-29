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
print('LONG dot at 08:31, dot_close=', dot)
print('cancel if low <= dot-40 =', dot - 40, ' within age 1..30 (confirmMins=30)')
print()
print('age  time   low     adverse(dot-low)  in_window  cancel?')
for k in range(0, 40):
    t, o, h, l, c = rows[di + k]
    adv = dot - l
    inwin = 1 <= k <= 30
    canc = inwin and adv >= 40
    print('%3d  %s  %.2f  %7.2f        %s      %s' % (k, t.strftime('%H:%M'), l, adv, 'yes' if inwin else 'NO ', 'CANCEL' if canc else ''))
    if canc:
        break
