import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

cols = list(r[0].keys())
print('PARAMS:', {c.replace('P_', ''): r[600][c].strip() for c in cols if c.startswith('P_')})
print('exit-type columns present:', [c for c in cols if 'exit' in c.lower() or 'entry' in c.lower() or 'cancel' in c.lower()])
print()

targets = ['07-Jul 00:5', '07-Jul 01:', '08-Jul 01:4', '08-Jul 06:4', '08-Jul 07:0']

def show(daylabel, lo_h, lo_m, hi_h, hi_m):
    print('=== %s ===' % daylabel)
    for row in r:
        t = datetime.fromisoformat(row['time']).astimezone(LDN)
        d = t.strftime('%d-%b')
        mm = t.hour * 60 + t.minute
        if d == daylabel and lo_h * 60 + lo_m <= mm <= hi_h * 60 + hi_m:
            ev = []
            for cn in ('long entry', 'short entry', 'exit', 'dbl bottom exit', 'dbl top exit'):
                if nz(row.get(cn, '')):
                    ev.append(cn)
            live = (row.get('live (1/0)', '') or '').strip()
            wn = (row.get('live win N', '') or '').strip()
            print(t.strftime('%H:%M'), 'O=' + row['open'], 'H=' + row['high'], 'L=' + row['low'], 'C=' + row['close'],
                  'live=' + (live or '-'), 'N=' + (wn or '-'), ' '.join(ev))
    print()

show('07-Jul', 0, 50, 1, 40)
show('08-Jul', 1, 40, 2, 5)
show('08-Jul', 6, 45, 7, 15)
