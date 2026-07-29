import csv
from collections import Counter

r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

def fo(row, k):
    return float(row[k])

EXITCOLS = ['break exit', 'cancel exit', 'dbl bottom exit', 'dbl top exit', 'wick exit (short)', 'wick exit (long)']

def isexit(row):
    return any(nz(row.get(c, '')) for c in EXITCOLS)

def exitkind(row):
    for c in EXITCOLS:
        if nz(row.get(c, '')):
            return c
    return None

n = len(r)
trades = []
i = 0
while i < n:
    row = r[i]
    il = nz(row.get('long entry', '')); iss = nz(row.get('short entry', ''))
    if il or iss:
        if i + 1 >= n:
            break
        d = 1 if il else -1; eb = i + 1; entry = fo(r[eb], 'open')
        wn = (r[eb].get('live win N', '') or '').strip()
        try:
            N = int(float(wn))
        except:
            N = None
        j = eb; xb = None; kind = None
        while j < n:
            if isexit(r[j]):
                xb = j + 1; kind = exitkind(r[j]); break
            j += 1
        if xb is None or xb >= n:
            xb = min(j, n - 1)
        xpx = fo(r[xb], 'open'); pnl = (xpx - entry) if d > 0 else (entry - xpx)
        trades.append({'winN': N, 'dir': d, 'pnl': pnl, 'won': pnl > 0, 'kind': kind})
        i = xb
    else:
        i += 1

print('trades %d, net %.0f, win%% %.0f' % (len(trades), sum(t['pnl'] for t in trades),
                                            100 * sum(1 for t in trades if t['won']) / len(trades)))
print()

def report(sub, lbl):
    if not sub:
        print('%-24s none' % lbl); return
    w = [t for t in sub if t['won']]
    l = [t for t in sub if not t['won']]
    print('%-24s n=%2d | wins %2d (+%5.0f) | losses %2d (%6.0f) | NET %6.0f | win%% %3.0f' % (
        lbl, len(sub), len(w), sum(t['pnl'] for t in w), len(l), sum(t['pnl'] for t in l),
        sum(t['pnl'] for t in sub), 100 * len(w) / len(sub)))

print('=== winN buckets (win/loss/net) ===')
report([t for t in trades if t['winN'] and t['winN'] <= 60], 'winN = 60')
report([t for t in trades if t['winN'] and 70 <= t['winN'] <= 90], 'winN 70-90')
report([t for t in trades if t['winN'] and 100 <= t['winN'] <= 130], 'winN 100-130 (up to p75)')
report([t for t in trades if t['winN'] and t['winN'] > 130], 'winN > 130 (p75 TAIL)')
print()
print('=== the > p75 (>130) tail, each trade ===')
for t in sorted([x for x in trades if x['winN'] and x['winN'] > 130], key=lambda x: x['winN']):
    print('  N=%3d %s  pnl %6.1f  %-16s %s' % (t['winN'], 'L' if t['dir'] > 0 else 'S', t['pnl'], t['kind'], 'WIN' if t['won'] else 'loss'))
print()
report([t for t in trades if t['winN'] and t['winN'] <= 130], 'winN <= 130 (would KEEP)')
report([t for t in trades if t['winN'] and t['winN'] <= 80], 'winN <= 80 (median cap)')
