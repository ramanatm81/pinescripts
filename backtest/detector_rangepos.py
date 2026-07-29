from trenddet_common import load, day_indices, TREND_DAYS, CHOP_DAYS, score_separation
from collections import deque


def aroon_signal(h, l, N, thr):
    n = len(h)
    sig = [0] * n
    osc = [0.0] * n
    for i in range(n):
        lo = max(0, i - N + 1)
        w = i - lo + 1
        hh = -1e18
        ll = 1e18
        bsh = 0
        bsl = 0
        for j in range(lo, i + 1):
            if h[j] >= hh:
                hh = h[j]
                bsh = i - j
            if l[j] <= ll:
                ll = l[j]
                bsl = i - j
        au = (w - bsh) / w * 100.0
        ad = (w - bsl) / w * 100.0
        o = ad - au
        osc[i] = o
        if o >= thr:
            sig[i] = -1
        elif o <= -thr:
            sig[i] = 1
    return sig


def day_score(sig, idxs, want):
    tgt = 1 if want == "up" else -1
    corr = wrong = 0
    for i in idxs:
        if sig[i] == tgt:
            corr += 1
        elif sig[i] != 0:
            wrong += 1
    n = len(idxs)
    return (corr - wrong) / n if n else 0.0


def run(N, thr):
    d = load()
    by = day_indices(d["t"])
    sig = aroon_signal(d["h"], d["l"], N, thr)
    dm = {}
    for day, idxs in by.items():
        if day in TREND_DAYS:
            dm[day] = day_score(sig, idxs, TREND_DAYS[day])
        elif day in CHOP_DAYS:
            up = day_score(sig, idxs, "up")
            dn = day_score(sig, idxs, "down")
            dm[day] = max(up, dn)
    return dm


best = None
for N in (120, 180, 240, 360, 480):
    for thr in (50, 60, 70, 80):
        dm = run(N, thr)
        sep = score_separation(dm)
        if sep is None:
            continue
        g = sep["gap"]
        if best is None or g > best[0]:
            best = (g, N, thr, dm, sep)

g, N, thr, dm, sep = best
print("BEST N=%d thr=%d gap=%.4f clean=%s" % (N, thr, g, sep["clean_separation"]))
for day in sorted(dm):
    tag = TREND_DAYS.get(day, "CHOP")
    print("  %s %-5s %.4f" % (day, tag, dm[day]))
print("trend_range", sep["trend_range"], "chop_range", sep["chop_range"])
d = load()
by = day_indices(d["t"])
sig = aroon_signal(d["h"], d["l"], N, thr)
di = by["2026-07-16"]
dn = sum(1 for i in di if sig[i] == -1)
up = sum(1 for i in di if sig[i] == 1)
print("07-16 bars=%d down=%d up=%d fires_down=%s" % (len(di), dn, up, dn > up and dn > 0))
