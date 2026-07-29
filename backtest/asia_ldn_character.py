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
        pnl = (exitpx - entry) if d > 0 else (entry - exitpx)
        mfe = (ext - entry) if d > 0 else (entry - ext)
        trades.append({'dir': d, 'pnl': pnl, 'reason': reason, 'mfe': mfe, 'life': exit_bar - eb,
                       'hour': et.hour, 'entry_t': et, 'winN': (rows[eb].get('live win N', '') or '').strip()})
        i = exit_bar
    else:
        i += 1

def sess(h):
    if 23 <= h or h <= 6: return 'ASIA'
    if 7 <= h <= 11: return 'LDN_AM'
    return 'OTHER'

overnight = [t for t in trades if sess(t['hour']) in ('ASIA', 'LDN_AM')]
day = [t for t in trades if sess(t['hour']) == 'OTHER']

def summ(sub, lbl):
    w = [t for t in sub if t['reason'] == 'dbl']
    l = [t for t in sub if t['reason'] != 'dbl']
    print('%s: %d trades | dbl-win %d (%.0f%%) | net %.0f | avgMFE %.0f | avg life %.0f | avgLoserMFE %.0f' % (
        lbl, len(sub), len(w), 100 * len(w) / len(sub) if sub else 0, sum(t['pnl'] for t in sub),
        st.mean([t['mfe'] for t in sub]), st.mean([t['life'] for t in sub]),
        st.mean([t['mfe'] for t in l]) if l else 0))

summ(overnight, 'OVERNIGHT (ASIA+LDN_AM)')
summ(day, 'DAY (12:00-23:00)')
print()
print('=== overnight LOSERS -- character ===')
print('%-16s %3s %6s %-6s %5s %5s %4s' % ('entry', 'dir', 'pnl', 'reason', 'mfe', 'life', 'N'))
for t in sorted([x for x in overnight if x['pnl'] <= 0], key=lambda x: x['entry_t']):
    print('%-16s %3s %6.1f %-6s %5.0f %5d %4s' % (
        t['entry_t'].strftime('%a %d %H:%M'), 'L' if t['dir'] > 0 else 'S', t['pnl'], t['reason'], t['mfe'], t['life'], t['winN']))
print()
# key comparison: how far do overnight trades run vs day, and how often do they reach a dbl
on_dbl_rate = sum(1 for t in overnight if t['reason'] == 'dbl') / len(overnight)
day_dbl_rate = sum(1 for t in day if t['reason'] == 'dbl') / len(day)
print('reach-a-double-bottom rate: overnight %.0f%%  vs  day %.0f%%' % (100 * on_dbl_rate, 100 * day_dbl_rate))
print('overnight loser avg MFE (how far they went before failing): %.0f pt' % st.mean([t['mfe'] for t in overnight if t['pnl'] <= 0]))
print('day loser avg MFE: %.0f pt' % st.mean([t['mfe'] for t in day if t['pnl'] <= 0]))
