import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, float(row['open']), float(row['high']), float(row['low']), float(row['close'])))

print('10-Jul around 10:01 -- bar ranges and wicks (SHORT trade, extreme low ~29716):')
print('%-6s %8s %8s %8s %8s %6s %7s %7s' % ('time', 'open', 'high', 'low', 'close', 'range', 'upWick', 'dnWick'))
for t, o, h, l, c in rows:
    if t.strftime('%d-%b') == '10-Jul' and 9*60+55 <= t.hour*60+t.minute <= 10*60+15:
        rng = h - l
        upwick = h - max(o, c)
        dnwick = min(o, c) - l
        body = abs(c - o)
        print('%-6s %8.2f %8.2f %8.2f %8.2f %6.1f %7.1f %7.1f  (body %.1f)' % (
            t.strftime('%H:%M'), o, h, l, c, rng, upwick, dnwick, body))
