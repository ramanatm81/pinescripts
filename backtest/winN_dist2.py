import csv
from datetime import datetime, timezone, timedelta
import statistics as st
from collections import Counter

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

# winN of every entry: entry flag is on bar i, the winning N is in 'live win N' on that bar
entries = []
for i, row in enumerate(r):
    is_long = nz(row.get('long entry', ''))
    is_short = nz(row.get('short entry', ''))
    if is_long or is_short:
        # winN: try this bar's 'live win N', else the entry bar's start-N
        wn = (row.get('live win N', '') or '').strip()
        if not wn or not wn.replace('.', '').isdigit():
            wn = (row.get('start N (winning window)', '') or '').strip()
        try:
            N = int(float(wn))
        except:
            N = None
        entries.append({'dir': 1 if is_long else -1, 'winN': N,
                        't': datetime.fromisoformat(row['time']).astimezone(LDN)})

allN = [e['winN'] for e in entries if e['winN']]
print('entries: %d  (with winN: %d)' % (len(entries), len(allN)))
if not allN:
    # fallback: winN column may only populate on the bar AFTER entry (live starts next bar)
    print('no winN on entry bars -- checking bar+1')
    entries = []
    for i, row in enumerate(r):
        if (nz(row.get('long entry', '')) or nz(row.get('short entry', ''))) and i + 1 < len(r):
            wn = (r[i+1].get('live win N', '') or '').strip()
            try:
                N = int(float(wn))
            except:
                N = None
            entries.append({'dir': 1 if nz(row.get('long entry', '')) else -1, 'winN': N})
    allN = [e['winN'] for e in entries if e['winN']]
    print('with winN (bar+1): %d' % len(allN))

print()
print('winN stats: min %d  p25 %d  MEDIAN %d  p75 %d  max %d  mean %.0f' % (
    min(allN), sorted(allN)[len(allN)//4], st.median(allN), sorted(allN)[3*len(allN)//4], max(allN), st.mean(allN)))
print()
print('=== winN histogram (all %d entries) ===' % len(allN))
c = Counter(allN)
for N in sorted(c):
    print('N=%3d : %2d  %s' % (N, c[N], '#' * c[N]))
print()
print('=== by bucket ===')
for lo, hi in [(60, 60), (70, 90), (100, 130), (140, 180), (190, 240)]:
    cnt = sum(1 for N in allN if lo <= N <= hi)
    print('%d-%d : %d entries (%.0f%%)' % (lo, hi, cnt, 100 * cnt / len(allN)))
print()
print('LONG winN median:', st.median([e['winN'] for e in entries if e['winN'] and e['dir'] > 0]))
print('SHORT winN median:', st.median([e['winN'] for e in entries if e['winN'] and e['dir'] < 0]))
print('entries with winN <= 60 (smallest window):', sum(1 for N in allN if N <= 60), 'of', len(allN))
print('entries with winN >= 150 (big window):', sum(1 for N in allN if N >= 150), 'of', len(allN))
