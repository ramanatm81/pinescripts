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

DOTPX = rows[di][4]
PROVEN = 80.0
DBAWAY = 30.0
DBTOL = 8.0

ext = rows[di][3]
movedaway = False
print('SHORT dot 09:53, time gate REMOVED. proven>=80 dbAway=30 dbTol=8')
for k in range(0, 40):
    t, o, h, l, c = rows[di + k]
    pe = ext
    ext = min(ext, l)
    if ext < pe:
        movedaway = False
    if (h - ext) >= DBAWAY:
        movedaway = True
    favtrav = DOTPX - ext
    proven = favtrav >= PROVEN
    retestGap = l - ext
    dblexit = proven and movedaway and 0 <= retestGap <= DBTOL
    tag = 'DBLEXIT' if dblexit else ''
    print('age %2d  %s  L=%.2f ext=%.2f fav=%.0f proven=%s away=%s gap=%.2f  %s' % (
        k, t.strftime('%H:%M'), l, ext, favtrav, 'Y' if proven else 'n', 'Y' if movedaway else 'n', retestGap, tag))
    if dblexit:
        break
