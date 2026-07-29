import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))

def nz(v):
    return (v or '').strip() not in ('', 'NaN', '0')

rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, row))

p = {c.replace('P_', ''): r[600][c].strip() for c in r[0].keys() if c.startswith('P_')}
print('PARAMS:', {k: p[k] for k in ('adverseStopPts', 'provenPts', 'pullbackPts', 'pullbackFrac', 'dbAwayPts', 'dbTolPts')})
print()

di = None
for i, (t, row) in enumerate(rows):
    if t.strftime('%d-%b') == '10-Jul' and t.hour == 7 and t.minute == 43:
        di = i
        break

DIR = -1
dotpx = float(rows[di][1]['close'])
PROVEN = float(p['provenPts'])
ADV = float(p['adverseStopPts'])
PB = float(p['pullbackPts'])
FRAC = float(p['pullbackFrac'])
DBAWAY = float(p['dbAwayPts'])
DBTOL = float(p['dbTolPts'])

print('SHORT dot 10-Jul 07:43, dotClose=%.2f' % dotpx)
print('%-6s %8s %8s %7s %7s %6s %s %s' % ('time', 'high', 'low', 'favTrav', 'ext', 'proven', 'adv(H-dot)', 'event'))
ext = float(rows[di][1]['low'])
movedaway = False
startpx = dotpx
for k in range(0, 300):
    t, row = rows[di + k]
    h = float(row['high']); l = float(row['low']); c = float(row['close'])
    pe = ext
    ext = min(ext, l)
    newext = ext < pe
    if newext:
        movedaway = False
    if (h - ext) >= DBAWAY:
        movedaway = True
    fav = dotpx - ext
    proven = fav >= PROVEN
    adverse = h - dotpx
    effpb = max(PB, abs(ext - startpx) * FRAC)
    broke = c > ext + effpb
    advstop = ADV > 0 and k >= 1 and (not proven) and adverse >= ADV
    retest = l - ext
    dbl = proven and movedaway and (not newext) and 0 <= retest <= DBTOL
    ev = []
    if nz(row.get('exit', '')): ev.append('EXIT-marker')
    if nz(row.get('dbl bottom exit', '')): ev.append('DBL-marker')
    if advstop: ev.append('adverse-stop-would-fire')
    if broke: ev.append('pullback-break-would-fire')
    if dbl: ev.append('DBL-would-fire')
    if fav >= 80 and not proven: pass
    if ev or k % 10 == 0 or newext:
        print('%-6s %8.2f %8.2f %7.1f %7.2f %6s %10.1f %s' % (
            t.strftime('%H:%M'), h, l, fav, ext, 'Y' if proven else 'n', adverse, ' '.join(ev)))
    if nz(row.get('exit', '')) and k > 0:
        print('--- position exit marker here ---')
        break
