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
        entry_t = rows[eb]['_t']
        j = eb
        reason = 'none'; exit_bar = None
        while j < n:
            if nz(rows[j].get('dbl bottom exit', '')) or nz(rows[j].get('dbl top exit', '')):
                reason = 'dbl'; exit_bar = j + 1; break
            if nz(rows[j].get('exit', '')):
                reason = 'break'; exit_bar = j + 1; break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exitpx = fnum(rows[exit_bar], 'open')
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        trades.append({'dir': d, 'pnl': pnl, 'reason': reason, 'hour': entry_t.hour, 'entry_t': entry_t})
        i = exit_bar
    else:
        i += 1

def blocked(h):
    return h >= 23 or h < 12

blk = [t for t in trades if blocked(t['hour'])]
kep = [t for t in trades if not blocked(t['hour'])]

def summ(sub, lbl):
    if not sub:
        print(lbl, 'none'); return
    w = [t for t in sub if t['reason'] == 'dbl']
    print('%s: %d trades | wins(dbl) %d (%.0f%%) | net %.0f | grossW %.0f grossL %.0f' % (
        lbl, len(sub), len(w), 100 * len(w) / len(sub), sum(t['pnl'] for t in sub),
        sum(t['pnl'] for t in sub if t['pnl'] > 0), sum(t['pnl'] for t in sub if t['pnl'] <= 0)))

print('SESSION BLOCK = 23:00-11:59 London (entries here would be skipped)')
print()
summ(blk, 'BLOCKED (23:00-12:00)')
summ(kep, 'KEPT   (12:00-23:00)')
print()
print('=== the BLOCKED trades (what we would skip) ===')
print('%-16s %3s %7s %-6s' % ('entry', 'dir', 'pnl', 'reason'))
for t in sorted(blk, key=lambda x: x['entry_t']):
    print('%-16s %3s %7.1f %-6s' % (t['entry_t'].strftime('%a %d %H:%M'), 'L' if t['dir'] > 0 else 'S', t['pnl'], t['reason']))
print()
bw = [t for t in blk if t['pnl'] > 0]
bl = [t for t in blk if t['pnl'] <= 0]
print('blocked winners:', len(bw), 'totaling', round(sum(t['pnl'] for t in bw)))
print('blocked losers :', len(bl), 'totaling', round(sum(t['pnl'] for t in bl)))
print('net removed by the block:', round(sum(t['pnl'] for t in blk)))
print('strategy net WITHOUT the block:', round(sum(t['pnl'] for t in trades)))
print('strategy net WITH the block:   ', round(sum(t['pnl'] for t in kep)))
