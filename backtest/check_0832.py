import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN')

cols = list(r[0].keys())
has_evt = 'EVT_start_dir' in cols
print('columns kind:', 'STRATEGY' if 'short entry' in cols else 'DETECTOR')
print('PARAMS:', {c.replace('P_', ''): r[600][c].strip() for c in cols if c.startswith('P_')})
print()

for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    if t.strftime('%d-%b') == '24-Jul' and 8*60+25 <= t.hour*60+t.minute <= 9*60+10:
        fl = []
        for cn in ('long entry', 'short entry', 'exit'):
            v = (row.get(cn, '') or '').strip()
            if v not in ('', 'NaN', '0'):
                fl.append(cn + '=' + v)
        live = (row.get('live (1/0)', '') or '').strip()
        wn = (row.get('live win N', '') or '').strip()
        sn = (row.get('start N (winning window)', '') or '').strip()
        extra = ''
        if sn not in ('', 'NaN'):
            extra += ' START_N=' + sn
        print(t.strftime('%H:%M'), 'O=' + row['open'], 'H=' + row['high'], 'L=' + row['low'], 'C=' + row['close'],
              'live=' + (live or '-'), 'winN=' + (wn or '-'), extra, ' '.join(fl))
