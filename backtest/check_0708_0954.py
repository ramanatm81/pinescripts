import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN')

cols = list(r[0].keys())
print('kind:', 'STRATEGY' if 'short entry' in cols else 'DETECTOR')
print('PARAMS:', {c.replace('P_', ''): r[600][c].strip() for c in cols if c.startswith('P_')})
print()

for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    if t.strftime('%d-%b') == '08-Jul' and 9*60+30 <= t.hour*60+t.minute <= 11*60+0:
        ev = []
        for cn in ('long entry', 'short entry', 'exit'):
            v = (row.get(cn, '') or '').strip()
            if v not in ('', 'NaN', '0'):
                ev.append(cn + '=' + v)
        live = (row.get('live (1/0)', '') or '').strip()
        wn = (row.get('live win N', '') or '').strip()
        print(t.strftime('%H:%M'), 'O=' + row['open'], 'H=' + row['high'], 'L=' + row['low'], 'C=' + row['close'],
              'live=' + (live or '-'), 'winN=' + (wn or '-'), ' '.join(ev))
