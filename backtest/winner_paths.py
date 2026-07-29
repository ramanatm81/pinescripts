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
        j = eb
        reason = 'none'
        exit_bar = None
        path = []
        while j < n:
            fav = (fnum(rows[j], 'high') - entry) if d > 0 else (entry - fnum(rows[j], 'low'))
            adv = (entry - fnum(rows[j], 'low')) if d > 0 else (fnum(rows[j], 'high') - entry)
            path.append((fav, adv))
            if nz(rows[j].get('dbl bottom exit', '')) or nz(rows[j].get('dbl top exit', '')):
                reason = 'dbl'; exit_bar = j + 1; break
            if nz(rows[j].get('exit', '')):
                reason = 'break'; exit_bar = j + 1; break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exitpx = fnum(rows[exit_bar], 'open')
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        trades.append({'dir': d, 'pnl': pnl, 'reason': reason, 'path': path, 'entry_t': rows[eb]['_t']})
        i = exit_bar
    else:
        i += 1

wins = [t for t in trades if t['reason'] == 'dbl']

print('=== WINNER PATHS: after first reaching +ARM favorable, do they dip back below KEEP? ===')
print('This tells us if a breakeven/profit-lock stop would SCRATCH winners.')
print()
for ARM in (30, 40, 50, 60):
    for KEEP in (0, 10, 20):
        scratched = 0
        for t in wins:
            armed = False
            hit = False
            for (fav, adv) in t['path']:
                if fav >= ARM:
                    armed = True
                if armed and fav <= KEEP:
                    hit = True
                    break
            if hit:
                scratched += 1
        print('ARM +%d, stop-at +%d: would scratch %d of %d winners' % (ARM, KEEP, scratched, len(wins)))
    print()

print('=== For each winner: MFE, and the DEEPEST pullback AFTER first hitting +40 ===')
print('%-16s %3s %6s %8s %8s' % ('entry', 'dir', 'pnl', 'MFE', 'minFav_after40'))
for t in sorted(wins, key=lambda x: -x['pnl']):
    mfe = max(f for f, a in t['path'])
    armed = False
    minfav = None
    for (fav, adv) in t['path']:
        if fav >= 40:
            armed = True
        if armed:
            minfav = fav if minfav is None else min(minfav, fav)
    print('%-16s %3s %6.0f %8.0f %8s' % (
        t['entry_t'].strftime('%a %d %H:%M'), 'L' if t['dir'] > 0 else 'S', t['pnl'], mfe,
        ('%.0f' % minfav) if minfav is not None else 'n/a'))
