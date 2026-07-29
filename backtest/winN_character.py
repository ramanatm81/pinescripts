import csv
from datetime import datetime, timezone, timedelta
import statistics as st

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append(row | {'_t': t})

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

def fnum(row, k):
    return float(row[k])

n = len(rows)
trades = []
i = 0
while i < n:
    row = rows[i]
    is_long = nz(row.get('long entry', ''))
    is_short = nz(row.get('short entry', ''))
    if is_long or is_short:
        d = 1 if is_long else -1
        if i + 1 >= n:
            break
        eb = i + 1
        entry = fnum(rows[eb], 'open')
        winN = (rows[eb].get('live win N', '') or '').strip()
        j = eb
        reason = 'none'; exit_bar = None
        ext = fnum(rows[eb], 'high') if d > 0 else fnum(rows[eb], 'low')
        while j < n:
            ext = max(ext, fnum(rows[j], 'high')) if d > 0 else min(ext, fnum(rows[j], 'low'))
            if nz(rows[j].get('dbl bottom exit', '')) or nz(rows[j].get('dbl top exit', '')):
                reason = 'dbl'; exit_bar = j + 1; break
            if nz(rows[j].get('exit', '')):
                reason = 'break'; exit_bar = j + 1; break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exitpx = fnum(rows[exit_bar], 'open')
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        mfe = (ext - entry) if d > 0 else (entry - ext)
        trades.append({'dir': d, 'pnl': pnl, 'reason': reason, 'mfe': mfe,
                       'life': exit_bar - eb, 'winN': int(winN) if winN.isdigit() else None,
                       'entry_t': rows[eb]['_t']})
        i = exit_bar
    else:
        i += 1

def show(lo, hi):
    sub = [t for t in trades if t['winN'] and lo <= t['winN'] <= hi]
    if not sub:
        print('  none'); return
    w = [t for t in sub if t['reason'] == 'dbl']
    brk = [t for t in sub if t['reason'] == 'break']
    print('  %d trades | dbl-wins %d | break %d | net %.0f | avg MFE %.0f | avg life %.0f' % (
        len(sub), len(w), len(brk), sum(t['pnl'] for t in sub),
        st.mean([t['mfe'] for t in sub]), st.mean([t['life'] for t in sub])))
    for t in sorted(sub, key=lambda x: x['pnl']):
        print('    %-15s %s N=%3d %6.1f  %-6s mfe=%3.0f life=%3d' % (
            t['entry_t'].strftime('%a %d %H:%M'), 'L' if t['dir'] > 0 else 'S',
            t['winN'], t['pnl'], t['reason'], t['mfe'], t['life']))

print('=== N=100-130 (losing bucket) ===')
show(100, 130)
print()
print('=== N=190-240 (losing bucket, big/late windows) ===')
show(190, 240)
print()
print('=== N=70-90 (winning bucket, for contrast) ===')
show(70, 90)
