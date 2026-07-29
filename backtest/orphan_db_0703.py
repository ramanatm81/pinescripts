import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

cols = list(r[0].keys())
print('PARAMS:', {c.replace('P_', ''): r[600][c].strip() for c in cols if c.startswith('P_')})
print()

for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    if t.strftime('%d-%b') == '03-Jul' and 5*60+45 <= t.hour*60+t.minute <= 6*60+45:
        ev = []
        for cn in ('long entry', 'short entry', 'exit', 'dbl bottom exit', 'dbl top exit'):
            if nz(row.get(cn, '')):
                ev.append(cn)
        live = (row.get('live (1/0)', '') or '').strip()
        wn = (row.get('live win N', '') or '').strip()
        print(t.strftime('%H:%M'), 'O=' + row['open'], 'H=' + row['high'], 'L=' + row['low'], 'C=' + row['close'],
              'live=' + (live or '-'), 'winN=' + (wn or '-'), ' '.join(ev))
