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
    if t.strftime('%d-%b') == '10-Jul' and t.hour == 7 and t.minute == 43:
        di = i
        break

dotpx = rows[di][4]
PROVEN = 80.0
print('SHORT dot 10-Jul 07:43, dot=%.2f, proven at fav>=80' % dotpx)
print('wick (close - low) on fresh-extreme bars while proven+profitable:')
print('%-6s %8s %8s %8s %7s %7s %s' % ('time', 'low', 'close', 'fav', 'wick', 'proven', 'inProfit'))
ext = rows[di][3]
for k in range(0, 200):
    t, o, h, l, c = rows[di + k]
    pe = ext
    ext = min(ext, l)
    newext = ext < pe
    fav = dotpx - ext
    proven = fav >= PROVEN
    inprofit = c < dotpx
    wick = c - l   # short: how far it closed back up from the low
    if newext and (proven or fav >= 60):
        print('%-6s %8.2f %8.2f %7.1f %7.1f %7s %s' % (
            t.strftime('%H:%M'), l, c, fav, wick, 'Y' if proven else 'n', 'Y' if inprofit else 'n'))
