import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

p = {c.replace('P_', ''): r[600][c].strip() for c in r[0].keys() if c.startswith('P_')}
print('PARAMS:', {k: p.get(k) for k in ('enableWickEx', 'wickEntryPts', 'adverseStopPts', 'provenPts', 'confirmMins')})
print()

for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    if t.strftime('%d-%b') == '08-Jul' and 15*60+20 <= t.hour*60+t.minute <= 16*60+10:
        ev = []
        for cn in ('long entry', 'short entry', 'wick long entry', 'wick short entry',
                   'break exit', 'cancel exit', 'dbl bottom exit', 'dbl top exit'):
            if nz(row.get(cn, '')):
                ev.append(cn)
        live = (row.get('live (1/0)', '') or '').strip()
        wn = (row.get('live win N', '') or '').strip()
        lo = min(float(row['open']), float(row['close'])) - float(row['low'])
        hi = float(row['high']) - max(float(row['open']), float(row['close']))
        print(t.strftime('%H:%M'), 'O=' + row['open'], 'H=' + row['high'], 'L=' + row['low'], 'C=' + row['close'],
              'loWick=%.1f' % lo, 'live=' + (live or '-'), 'N=' + (wn or '-'), ' '.join(ev))
