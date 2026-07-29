import csv
from datetime import datetime, timezone, timedelta
import statistics as st

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

def fo(row, k):
    return float(row[k])

n = len(r)

# robust reconstruction: walk bars; on an entry flag, open a trade; its winN = live-win-N on the
# NEXT bar (live starts next bar). Close on the next exit/dbl marker. Do NOT skip entries: after
# closing, continue scanning from the exit bar.
trades = []
i = 0
while i < n:
    row = r[i]
    is_long = nz(row.get('long entry', ''))
    is_short = nz(row.get('short entry', ''))
    if (is_long or is_short) and i + 1 < n:
        d = 1 if is_long else -1
        eb = i + 1
        entry = fo(r[eb], 'open')
        wn = (r[eb].get('live win N', '') or '').strip()
        try:
            N = int(float(wn))
        except:
            N = None
        j = eb
        exit_bar = None
        while j < n:
            if nz(r[j].get('dbl bottom exit', '')) or nz(r[j].get('dbl top exit', '')) or nz(r[j].get('exit', '')):
                exit_bar = j + 1
                break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exitpx = fo(r[exit_bar], 'open')
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        trades.append({'dir': d, 'pnl': pnl, 'won': pnl > 0, 'winN': N})
        i = exit_bar
    else:
        i += 1

print('reconstructed trades: %d (expected ~76 entries; some entries share bars if back-to-back)' % len(trades))
tot_net = sum(t['pnl'] for t in trades)
tot_w = sum(1 for t in trades if t['won'])
print('overall: win%% %.0f, net %.0f' % (100*tot_w/len(trades), tot_net))
print()

def report(sub, lbl):
    if not sub:
        print(lbl, ': none'); return
    w = [t for t in sub if t['won']]
    l = [t for t in sub if not t['won']]
    print('%-22s n=%2d | wins %2d net %6.0f (avg %5.1f) | losses %2d net %6.0f (avg %5.1f) | TOTAL net %6.0f' % (
        lbl, len(sub), len(w), sum(t['pnl'] for t in w), (sum(t['pnl'] for t in w)/len(w)) if w else 0,
        len(l), sum(t['pnl'] for t in l), (sum(t['pnl'] for t in l)/len(l)) if l else 0,
        sum(t['pnl'] for t in sub)))

print('=== split by winN vs p75 (130) ===')
report([t for t in trades if t['winN'] and t['winN'] <= 130], 'winN <= 130 (keep)')
report([t for t in trades if t['winN'] and t['winN'] > 130], 'winN > 130 (p75 tail)')
print()
print('=== finer ===')
report([t for t in trades if t['winN'] and t['winN'] <= 80], 'winN <= 80 (<=median)')
report([t for t in trades if t['winN'] and 90 <= t['winN'] <= 130], 'winN 90-130')
report([t for t in trades if t['winN'] and 140 <= t['winN'] <= 180], 'winN 140-180')
report([t for t in trades if t['winN'] and t['winN'] >= 190], 'winN >= 190')
print()
print('=== each big-N (>130) trade ===')
for t in sorted([x for x in trades if x['winN'] and x['winN'] > 130], key=lambda x: x['winN']):
    print('  N=%3d  %s  pnl %6.1f  %s' % (t['winN'], 'L' if t['dir'] > 0 else 'S', t['pnl'], 'WIN' if t['won'] else 'loss'))
