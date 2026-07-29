import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, row))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

def fo(row, k):
    return float(row[k])

p = {c.replace('P_', ''): rows[600][1][c].strip() for c in rows[0][1].keys() if c.startswith('P_')}
PROVEN = float(p['provenPts'])
DBAWAY = float(p['dbAwayPts'])
DBTOL = float(p['dbTolPts'])
ADV = float(p['adverseStopPts'])
PB = float(p['pullbackPts'])
FRAC = float(p['pullbackFrac'])

n = len(rows)

def run(wick_thresh):
    trades = []
    i = 0
    while i < n:
        t, row = rows[i]
        d = 1 if nz(row.get('long entry', '')) else (-1 if nz(row.get('short entry', '')) else 0)
        if d != 0 and i + 1 < n:
            eb = i + 1
            entry = fo(rows[eb][1], 'open')
            dotpx = fo(row, 'close')
            startpx = dotpx
            ext = fo(rows[eb][1], 'high') if d > 0 else fo(rows[eb][1], 'low')
            movedaway = False
            j = eb
            exit_bar = None
            reason = 'none'
            while j < n:
                bt, brow = rows[j]
                h = fo(brow, 'high'); l = fo(brow, 'low'); c = fo(brow, 'close')
                pe = ext
                ext = max(ext, h) if d > 0 else min(ext, l)
                newext = (ext > pe) if d > 0 else (ext < pe)
                if newext:
                    movedaway = False
                off = (ext - l) if d > 0 else (h - ext)
                if off >= DBAWAY:
                    movedaway = True
                fav = (ext - dotpx) if d > 0 else (dotpx - ext)
                proven = fav >= PROVEN
                adverse = (dotpx - l) if d > 0 else (h - dotpx)
                age = j - eb
                inprofit = (c > dotpx) if d > 0 else (c < dotpx)
                wick = (h - c) if d > 0 else (c - l)
                # exits (order matters; cancel first, then wick, dbl, break)
                adv_stop = ADV > 0 and age >= 1 and (not proven) and adverse >= ADV
                retest = (ext - h) if d > 0 else (l - ext)
                dbl = proven and movedaway and (not newext) and 0 <= retest <= DBTOL
                wick_ex = wick_thresh > 0 and proven and inprofit and newext and wick >= wick_thresh
                effpb = max(PB, abs(ext - startpx) * FRAC)
                broke = (c < ext - effpb) if d > 0 else (c > ext + effpb)
                if adv_stop:
                    reason = 'cancel'; exit_bar = j + 1; break
                if wick_ex:
                    reason = 'wick'; exit_bar = j + 1; break
                if dbl:
                    reason = 'dbl'; exit_bar = j + 1; break
                if broke:
                    reason = 'break'; exit_bar = j + 1; break
                j += 1
            if exit_bar is None or exit_bar >= n:
                exit_bar = min(j, n - 1)
            exitpx = fo(rows[exit_bar][1], 'open')
            pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
            trades.append({'pnl': pnl, 'reason': reason, 'dir': d, 'entry_t': rows[eb][0]})
            i = exit_bar
        else:
            i += 1
    return trades

for wick in (0, 20, 30):
    tr = run(wick)
    w = [t for t in tr if t['pnl'] > 0]
    net = sum(t['pnl'] for t in tr)
    from collections import Counter
    rc = Counter(t['reason'] for t in tr)
    print('wick=%2d : %d trades, win%% %.0f, net %.0f | reasons %s' % (
        wick, len(tr), 100 * len(w) / len(tr), net, dict(rc)))
    if wick == 20:
        wex = [t for t in tr if t['reason'] == 'wick']
        print('   wick-exits: %d, of which winners %d, net %.0f' % (
            len(wex), sum(1 for t in wex if t['pnl'] > 0), sum(t['pnl'] for t in wex)))
