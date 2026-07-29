import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

cols = list(r[0].keys())
print('ALL COLUMNS:')
print(cols)
print()

for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    if t.strftime('%d-%b') == '24-Jul' and 14*60+56 <= t.hour*60+t.minute <= 14*60+59:
        print('=== ' + t.strftime('%a %d-%b %H:%M') + ' (raw time ' + row['time'] + ') ===')
        for c in cols:
            v = (row[c] or '').strip()
            if v not in ('', 'NaN'):
                print('   ' + c + ' = ' + v)
        print()
