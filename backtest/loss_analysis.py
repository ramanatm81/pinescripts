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
        entry_bar = i + 1
        entry_px = fnum(rows[entry_bar], 'open')
        entry_t = rows[entry_bar]['_t']
        j = entry_bar
        ext = fnum(rows[entry_bar], 'high') if d > 0 else fnum(rows[entry_bar], 'low')
        exit_bar = None
        exit_reason = 'none'
        while j < n:
            ext = max(ext, fnum(rows[j], 'high')) if d > 0 else min(ext, fnum(rows[j], 'low'))
            if nz(rows[j].get('dbl bottom exit', '')) or nz(rows[j].get('dbl top exit', '')):
                exit_reason = 'dbl'
                exit_bar = j + 1
                break
            if nz(rows[j].get('exit', '')):
                exit_reason = 'break'
                exit_bar = j + 1
                break
            j += 1
        if exit_bar is None or exit_bar >= n:
            exit_bar = min(j, n - 1)
        exit_px = fnum(rows[exit_bar], 'open')
        exit_t = rows[exit_bar]['_t']
        pnl = (exit_px - entry_px) if d > 0 else (entry_px - exit_px)
        life = exit_bar - entry_bar
        mfe = (ext - entry_px) if d > 0 else (entry_px - ext)
        trades.append({
            'dir': d, 'entry_t': entry_t, 'entry_px': entry_px, 'exit_t': exit_t,
            'exit_px': exit_px, 'pnl': pnl, 'life': life, 'mfe': mfe, 'reason': exit_reason,
            'winN': (rows[entry_bar].get('live win N', '') or '').strip(),
        })
        i = exit_bar
    else:
        i += 1

wins = [t for t in trades if t['pnl'] > 0]
losses = [t for t in trades if t['pnl'] <= 0]
net = sum(t['pnl'] for t in trades)
gw = sum(t['pnl'] for t in wins)
gl = sum(t['pnl'] for t in losses)
pf = gw / abs(gl) if gl else 0

print('=== OVERALL (reconstructed from indicator signals, MNQ points) ===')
print('trades %d | wins %d (%.0f%%) | losses %d | net %.0f | PF %.2f' % (
    len(trades), len(wins), 100 * len(wins) / len(trades), len(losses), net, pf))
print('gross win %.0f  gross loss %.0f  avgW %.1f  avgL %.1f' % (
    gw, gl, gw / len(wins) if wins else 0, gl / len(losses) if losses else 0))
print()

print('=== BY DIRECTION ===')
for d, lbl in ((1, 'LONG'), (-1, 'SHORT')):
    sub = [t for t in trades if t['dir'] == d]
    w = [t for t in sub if t['pnl'] > 0]
    if not sub:
        continue
    print('%s: %d trades, win%% %.0f, net %.0f, avgW %.1f, avgL %.1f' % (
        lbl, len(sub), 100 * len(w) / len(sub), sum(t['pnl'] for t in sub),
        (sum(t['pnl'] for t in w) / len(w)) if w else 0,
        (sum(t['pnl'] for t in sub if t['pnl'] <= 0) / max(1, len(sub) - len(w)))))
print()

print('=== BY EXIT REASON ===')
for reason in ('break', 'dbl'):
    sub = [t for t in trades if t['reason'] == reason]
    if not sub:
        continue
    w = [t for t in sub if t['pnl'] > 0]
    print('%s: %d trades, win%% %.0f, net %.0f' % (reason, len(sub), 100 * len(w) / len(sub), sum(t['pnl'] for t in sub)))
print()

print('=== LOSERS detail (sorted worst first) ===')
print('%-16s %3s %7s %7s %6s %5s %5s %5s' % ('entry', 'dir', 'entry', 'exit', 'pnl', 'life', 'mfe', 'N'))
for t in sorted(losses, key=lambda x: x['pnl']):
    print('%-16s %3s %7.0f %7.0f %6.1f %5d %5.0f %5s' % (
        t['entry_t'].strftime('%a %d %H:%M'), 'L' if t['dir'] > 0 else 'S',
        t['entry_px'], t['exit_px'], t['pnl'], t['life'], t['mfe'], t['winN']))
print()

print('=== LOSER attributes ===')
llife = [t['life'] for t in losses]
lmfe = [t['mfe'] for t in losses]
print('loser life bars: median %.0f  mean %.0f  max %.0f' % (st.median(llife), st.mean(llife), max(llife)))
print('loser MFE (favorable pts before losing): median %.0f  mean %.0f  max %.0f' % (st.median(lmfe), st.mean(lmfe), max(lmfe)))
print('losers that NEVER went favorable (mfe<=5):', sum(1 for t in losses if t['mfe'] <= 5))
print('losers with mfe>=40 (gave back a real gain):', sum(1 for t in losses if t['mfe'] >= 40))
print('winner MFE median:', st.median([t['mfe'] for t in wins]) if wins else 0)
