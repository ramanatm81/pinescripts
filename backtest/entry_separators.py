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
        trades.append({'dir': d, 'pnl': pnl, 'reason': reason, 'winN': int(winN) if winN.isdigit() else None,
                       'hour': entry_t.hour, 'won': reason == 'dbl'})
        i = exit_bar
    else:
        i += 1

W = [t for t in trades if t['won']]
L = [t for t in trades if not t['won']]

def rate(sub):
    if not sub:
        return '0/0'
    w = sum(1 for t in sub if t['won'])
    return '%d/%d = %.0f%% win, net %.0f' % (w, len(sub), 100 * w / len(sub), sum(t['pnl'] for t in sub))

print('winners(dbl) %d  losers(break) %d' % (len(W), len(L)))
print()
print('=== winN (winning window at entry) ===')
print('winners winN: median', st.median([t['winN'] for t in W if t['winN']]), ' values', sorted(t['winN'] for t in W if t['winN']))
print('losers  winN: median', st.median([t['winN'] for t in L if t['winN']]), ' values', sorted(t['winN'] for t in L if t['winN']))
print()
print('=== win rate by winN bucket ===')
for lo, hi in ((60, 60), (70, 90), (100, 130), (140, 180), (190, 240)):
    sub = [t for t in trades if t['winN'] and lo <= t['winN'] <= hi]
    print('N %3d-%3d: %s' % (lo, hi, rate(sub)))
print()
print('=== win rate by entry HOUR (London) ===')
for h in range(0, 24):
    sub = [t for t in trades if t['hour'] == h]
    if sub:
        print('%02d:00 : %s' % (h, rate(sub)))
print()
print('=== win rate by direction ===')
for d, lbl in ((1, 'LONG'), (-1, 'SHORT')):
    print('%s: %s' % (lbl, rate([t for t in trades if t['dir'] == d])))
print()
print('=== session buckets (London) ===')
def sess(h):
    if 23 <= h or h <= 6: return 'ASIA 23-07'
    if 7 <= h <= 11: return 'LDN_AM 07-12'
    if 12 <= h <= 14: return 'LDN/US 12-15'
    if 15 <= h <= 16: return 'US_OPEN 15-17'
    return 'US_PM 17-23'
for s in ('ASIA 23-07', 'LDN_AM 07-12', 'LDN/US 12-15', 'US_OPEN 15-17', 'US_PM 17-23'):
    sub = [t for t in trades if sess(t['hour']) == s]
    print('%-14s: %s' % (s, rate(sub)))
