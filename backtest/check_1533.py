import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, float(row['open']), float(row['high']), float(row['low']), float(row['close'])))

print('10-Jul around 15:20-16:00 -- bar ranges/wicks (looking for long-lower-wick = up-trend signal):')
print('%-6s %8s %8s %8s %8s %6s %7s %7s' % ('time', 'open', 'high', 'low', 'close', 'range', 'loWick', 'hiWick'))
for t, o, h, l, c in rows:
    if t.strftime('%d-%b') == '10-Jul' and 15*60+20 <= t.hour*60+t.minute <= 16*60+0:
        rng = h - l
        lowick = min(o, c) - l
        hiwick = h - max(o, c)
        body = abs(c - o)
        mark = ''
        if lowick >= 15:
            mark = ' <== long LOWER wick'
        if hiwick >= 15:
            mark += ' <== long UPPER wick'
        print('%-6s %8.2f %8.2f %8.2f %8.2f %6.1f %7.1f %7.1f  body %.1f%s' % (
            t.strftime('%H:%M'), o, h, l, c, rng, lowick, hiwick, body, mark))
