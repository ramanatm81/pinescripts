import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN')

pcols = [c for c in r[0].keys() if c.startswith('P_')]
print('PARAMS:', {c.replace('P_', ''): r[600][c].strip() for c in pcols})
print('last row:', r[-1]['time'])
print()

for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    if t.strftime('%d-%b') == '24-Jul' and 14*60+50 <= t.hour*60+t.minute <= 15*60+12:
        fl = []
        if nz(row.get('EVT_start_dir', '')):
            fl.append('START dir=' + row['EVT_start_dir'].strip() + ' N=' + (row.get('EVT_win_N', '').strip() or '?'))
        if nz(row.get('EVT_break_dir', '')):
            fl.append('BREAK dir=' + row['EVT_break_dir'].strip() + ' life=' + (row.get('EVT_life_bars', '').strip() or '?') + ' travel=' + (row.get('EVT_travel', '').strip() or '?'))
        ll = (row.get('live length (bars)', '') or '').strip()
        print(t.strftime('%H:%M'), 'O=' + row['open'], 'H=' + row['high'], 'L=' + row['low'], 'C=' + row['close'], 'len=' + (ll or '-'), ' '.join(fl))
