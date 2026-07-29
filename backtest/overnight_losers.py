import csv
from datetime import datetime, timezone, timedelta

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
        et = rows[eb]['_t']
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
        exit_t = rows[exit_bar]['_t']
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        mfe = (ext - entry) if d > 0 else (entry - ext)
        trades.append({'dir': d, 'pnl': pnl, 'reason': reason, 'mfe': mfe, 'life': exit_bar - eb,
                       'hour': et.hour, 'entry_t': et, 'exit_t': exit_t, 'entry': entry, 'exit': exitpx,
                       'winN': (rows[eb].get('live win N', '') or '').strip()})
        i = exit_bar
    else:
        i += 1

def blocked(h):
    return h >= 23 or h < 12

losers = [t for t in trades if blocked(t['hour']) and t['pnl'] <= 0]
losers.sort(key=lambda x: x['entry_t'])

print('LOSERS in the blocked window (23:00-12:00 London), %d total, sum %.0f pt' % (
    len(losers), sum(t['pnl'] for t in losers)))
print()
print('%-16s %3s %8s %8s %7s %-6s %5s %5s %4s' % ('entry', 'dir', 'entryPx', 'exitPx', 'pnl', 'exit', 'mfe', 'life', 'N'))
for t in losers:
    print('%-16s %3s %8.0f %8.0f %7.1f %-6s %5.0f %5d %4s' % (
        t['entry_t'].strftime('%a %d %H:%M'), 'L' if t['dir'] > 0 else 'S',
        t['entry'], t['exit'], t['pnl'], t['reason'], t['mfe'], t['life'], t['winN']))
print()
print('by hour:')
from collections import defaultdict
byh = defaultdict(lambda: [0, 0.0])
for t in losers:
    byh[t['hour']][0] += 1
    byh[t['hour']][1] += t['pnl']
for h in sorted(byh):
    print('  %02d:00  %d losers  %.0f pt' % (h, byh[h][0], byh[h][1]))
