import csv
from datetime import datetime, timezone, timedelta

LDN = timezone(timedelta(hours=1))
r = list(csv.DictReader(open('/Users/maheshk81/Downloads/data.csv', encoding='utf-8-sig')))
rows = []
for row in r:
    t = datetime.fromisoformat(row['time']).astimezone(LDN)
    rows.append((t, float(row['open']), float(row['high']), float(row['low']), float(row['close'])))

di = None
for i, (t, o, h, l, c) in enumerate(rows):
    if t.strftime('%d-%b') == '08-Jul' and t.hour == 9 and t.minute == 53:
        di = i
        break

DIR = -1
DOTPX = rows[di][4]
PROVEN = 80.0
DBMIN = 20
DBAWAY = 30.0
DBTOL = 8.0

ext = rows[di][3]
extbar = di
movedaway = False
print('SHORT dot 09:53 dotPx=', DOTPX, ' proven>=', PROVEN, ' dbMin=', DBMIN, ' dbAway=', DBAWAY, ' dbTol=', DBTOL)
print('age  time   L        ext     favTrav proven movedAway barsSinceExt retestGap  DBLEXIT?')
for k in range(0, 75):
    t, o, h, l, c = rows[di + k]
    pe = ext
    ext = min(ext, l)
    if ext < pe:
        extbar = di + k
        movedaway = False
    offext = h - ext
    if offext >= DBAWAY:
        movedaway = True
    favtrav = DOTPX - ext
    proven = favtrav >= PROVEN
    barsSince = (di + k) - extbar
    retestGap = l - ext
    dblexit = proven and movedaway and (barsSince >= DBMIN) and 0 <= retestGap <= DBTOL
    print('%3d  %s  %.2f  %.2f  %6.1f   %s     %s      %4d       %6.2f    %s' % (
        k, t.strftime('%H:%M'), l, ext, favtrav, 'Y' if proven else 'n', 'Y' if movedaway else 'n', barsSince, retestGap, 'DBLEXIT' if dblexit else ''))
    if dblexit:
        break
