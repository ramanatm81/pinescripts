import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

di = None
allrows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    allrows.append((t, row))
    if t.strftime('%d-%b') == '08-Jul' and t.hour == 1 and t.minute == 42:
        di = len(allrows) - 1

print('LONG dot 08-Jul 01:42. Scanning forward for the exit event...')
for k in range(di, di + 120):
    t, row = allrows[k]
    ev = []
    for cn in ('exit', 'dbl bottom exit', 'dbl top exit', 'long entry', 'short entry'):
        if nz(row.get(cn, '')):
            ev.append(cn)
    if ev:
        print('  %s : %s   (close=%s low=%s high=%s)' % (t.strftime('%d %H:%M'), ', '.join(ev), row['close'], row['low'], row['high']))
    if any('exit' in e for e in ev) and k > di:
        break
