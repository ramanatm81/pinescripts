import csv
from datetime import datetime, timezone, timedelta
import statistics as st
from collections import Counter

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

# reconstruct trades: winN at entry, dir, outcome (dbl win vs break/cancel loss)
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
        while j < n:
            if nz(rows[j].get('dbl bottom exit', '')) or nz(rows[j].get('dbl top exit', '')):
                reason = 'dbl'; exit_bar = j + 1; break
            if nz(rows[j].get('exit', '')):
                reason = 'exit'; exit_bar = j + 1; break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exitpx = fnum(rows[exit_bar], 'open')
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        trades.append({'dir': d, 'pnl': pnl, 'won': pnl > 0,
                       'winN': int(winN) if winN.isdigit() else None})
        i = exit_bar
    else:
        i += 1

allN = [t['winN'] for t in trades if t['winN']]
print('total trades %d, with winN %d' % (len(trades), len(allN)))
print('winN: min %d  p25 %d  median %d  p75 %d  max %d  mean %.0f' % (
    min(allN), sorted(allN)[len(allN)//4], st.median(allN), sorted(allN)[3*len(allN)//4], max(allN), st.mean(allN)))
print()
print('=== distribution (count + win-rate + net by winN bucket) ===')
print('%-10s %6s %6s %7s %8s' % ('bucket', 'count', 'wins', 'win%', 'net'))
buckets = [(60, 60), (70, 90), (100, 130), (140, 180), (190, 240)]
for lo, hi in buckets:
    sub = [t for t in trades if t['winN'] and lo <= t['winN'] <= hi]
    if not sub:
        print('%-10s %6d' % ('%d-%d' % (lo, hi), 0)); continue
    w = sum(1 for t in sub if t['won'])
    print('%-10s %6d %6d %6.0f%% %8.0f' % ('%d-%d' % (lo, hi), len(sub), w, 100*w/len(sub), sum(t['pnl'] for t in sub)))
print()
print('=== exact winN histogram ===')
c = Counter(allN)
for N in sorted(c):
    sub = [t for t in trades if t['winN'] == N]
    w = sum(1 for t in sub if t['won'])
    bar = '#' * c[N]
    print('N=%3d : %2d trades  win%% %3.0f  net %6.0f  %s' % (N, c[N], 100*w/len(sub), sum(t['pnl'] for t in sub), bar))
print()
# is big-N systematically worse?
small = [t for t in trades if t['winN'] and t['winN'] <= 90]
big = [t for t in trades if t['winN'] and t['winN'] >= 140]
def wr(s): return (sum(1 for t in s if t['won'])/len(s)*100, sum(t['pnl'] for t in s)) if s else (0,0)
print('N<=90  : %d trades, win%% %.0f, net %.0f' % (len(small), *wr(small)))
print('N>=140 : %d trades, win%% %.0f, net %.0f' % (len(big), *wr(big)))
