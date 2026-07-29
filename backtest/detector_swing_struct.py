import sys
from trenddet_common import load, day_indices, TREND_DAYS, CHOP_DAYS, score_separation


def confirmed_pivots(h, l, L):
    n = len(h)
    piv = []
    for i in range(L, n - L):
        wh = h[i - L:i + L + 1]
        wl = l[i - L:i + L + 1]
        if h[i] == max(wh) and wh.count(h[i]) == 1:
            piv.append((i + L, i, "H", h[i]))
        elif l[i] == min(wl) and wl.count(l[i]) == 1:
            piv.append((i + L, i, "L", l[i]))
    piv.sort()
    return piv


def run(L=12, decay=0.85, thresh=0.30, agree=3, mag_norm=40.0):
    d = load()
    h, l, c = d["h"], d["l"], d["c"],
    c = d["c"]
    n = d["n"]
    by = day_indices(d["t"])

    piv = confirmed_pivots(h, l, L)
    conf_by_bar = {}
    for confbar, origin, kind, price in piv:
        conf_by_bar.setdefault(confbar, []).append((origin, kind, price))

    sig = [0] * n
    seqH = []
    seqL = []
    for i in range(n):
        if i in conf_by_bar:
            for origin, kind, price in conf_by_bar[i]:
                if kind == "H":
                    seqH.append((origin, price))
                else:
                    seqL.append((origin, price))
        score = 0.0
        wsum = 0.0
        for seq in (seqH, seqL):
            for k in range(len(seq) - 1, 0, -1):
                step = seq[k][1] - seq[k - 1][1]
                age = (len(seq) - 1) - k
                w = decay ** age
                score += w * (step / mag_norm)
                wsum += w
                if age >= agree:
                    break
        if wsum > 0:
            score /= wsum
        recent_ok = True
        if len(seqH) >= 2 and len(seqL) >= 2:
            hd = seqH[-1][1] - seqH[-2][1]
            ld = seqL[-1][1] - seqL[-2][1]
            if score > 0 and not (hd > 0 and ld > 0):
                recent_ok = False
            if score < 0 and not (hd < 0 and ld < 0):
                recent_ok = False
        else:
            recent_ok = False
        if recent_ok and score >= thresh:
            sig[i] = 1
        elif recent_ok and score <= -thresh:
            sig[i] = -1
        else:
            sig[i] = 0

    dm = {}
    for day, idx in by.items():
        if day not in TREND_DAYS and day not in CHOP_DAYS:
            continue
        want = TREND_DAYS.get(day)
        wantsign = 1 if want == "up" else (-1 if want == "down" else 0)
        nb = len(idx)
        correct = wrong = 0
        for i in idx:
            if sig[i] == 0:
                continue
            if wantsign != 0 and sig[i] == wantsign:
                correct += 1
            else:
                wrong += 1
        dm[day] = (correct - wrong) / nb
    return dm, sig, by


if __name__ == "__main__":
    best = None
    for L in (10, 12, 15, 20):
        for decay in (0.8, 0.85, 0.9):
            for thresh in (0.2, 0.3, 0.4):
                dm, sig, by = run(L=L, decay=decay, thresh=thresh)
                sep = score_separation(dm)
                gap = sep["gap"]
                d16 = dm.get("2026-07-16", 0)
                key = (gap, d16)
                if best is None or key > best[0]:
                    best = (key, L, decay, thresh, dm, sep)
    key, L, decay, thresh, dm, sep = best
    print("BEST L=%d decay=%.2f thresh=%.2f" % (L, decay, thresh))
    for day in sorted(dm):
        lab = "TREND-" + TREND_DAYS[day] if day in TREND_DAYS else "CHOP"
        print("  %s %8s  %+.3f" % (day, lab, dm[day]))
    print("sep:", sep)
    print("07-16 down:", dm.get("2026-07-16", 0) > 0)
