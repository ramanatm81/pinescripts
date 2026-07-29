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
        j = eb
        exit_bar = None
        bars = []
        while j < n:
            bars.append((fnum(rows[j], 'high'), fnum(rows[j], 'low'), fnum(rows[j], 'open')))
            if nz(rows[j].get('dbl bottom exit', '')) or nz(rows[j].get('dbl top exit', '')) or nz(rows[j].get('exit', '')):
                exit_bar = j + 1
                break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exitpx = fnum(rows[exit_bar], 'open')
        base_pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        trades.append({'dir': d, 'entry': entry, 'exitpx': exitpx, 'base': base_pnl, 'bars': bars})
        i = exit_bar
    else:
        i += 1

def base_net():
    return sum(t['base'] for t in trades)

def sim_be(arm, keep):
    net = 0.0
    scratched = 0
    saved = 0
    for t in trades:
        d = t['dir']; entry = t['entry']
        armed = False
        pnl = t['base']
        stopped = False
        for (h, l, o) in t['bars']:
            fav = (h - entry) if d > 0 else (entry - l)
            adv_low = l if d > 0 else h
            if armed:
                stop_px = entry + keep if d > 0 else entry - keep
                hit = (l <= stop_px) if d > 0 else (h >= stop_px)
                if hit:
                    pnl = keep
                    stopped = True
                    break
            if fav >= arm:
                armed = True
        if stopped:
            if t['base'] > keep:
                scratched += 1
            else:
                saved += 1
        net += pnl
    return net, scratched, saved

print('base net: %.0f' % base_net())
print('base wins/losses: %d / %d' % (sum(1 for t in trades if t['base'] > 0), sum(1 for t in trades if t['base'] <= 0)))
print()
print('breakeven-stop sim (arm at +A, stop moves to entry+KEEP):')
print('%5s %5s %8s %8s %10s %10s' % ('arm', 'keep', 'net', 'delta', 'scratched', 'saved'))
b = base_net()
for arm in (40, 50, 60, 70, 80):
    for keep in (0, 10, 20):
        net, sc, sv = sim_be(arm, keep)
        print('%5d %5d %8.0f %8.0f %10d %10d' % (arm, keep, net, net - b, sc, sv))
    print()
