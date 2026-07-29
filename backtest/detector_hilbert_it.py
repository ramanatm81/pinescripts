from trenddet_common import load, day_indices, TREND_DAYS, CHOP_DAYS, score_separation


def wma(vals, i, n):
    if i + 1 < n:
        n = i + 1
    num = 0.0
    den = 0.0
    for k in range(n):
        w = n - k
        num += w * vals[i - k]
        den += w
    return num / den


def hma_series(c):
    n = len(c)
    half = HMA_LEN // 2
    sq = int(HMA_LEN ** 0.5)
    raw = [0.0] * n
    for i in range(n):
        raw[i] = 2.0 * wma(c, i, half) - wma(c, i, HMA_LEN)
    hma = [0.0] * n
    for i in range(n):
        num = 0.0
        den = 0.0
        m = sq if i + 1 >= sq else i + 1
        for k in range(m):
            w = m - k
            num += w * raw[i - k]
            den += w
        hma[i] = num / den
    return hma


def atr_series(h, l, c):
    n = len(c)
    tr = [0.0] * n
    for i in range(n):
        if i == 0:
            tr[i] = h[i] - l[i]
        else:
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = [0.0] * n
    a = tr[0]
    for i in range(n):
        a = (a * (ATR_LEN - 1) + tr[i]) / ATR_LEN
        atr[i] = a
    return atr


HMA_LEN = 160
ATR_LEN = 60
SLOPE_BARS = 45
K = 0.45
PERSIST = 5


def signal_series(d):
    c = d["c"]
    h = d["h"]
    l = d["l"]
    n = d["n"]
    hma = hma_series(c)
    atr = atr_series(h, l, c)
    sig = [0] * n
    up_run = 0
    dn_run = 0
    for i in range(n):
        j = i - SLOPE_BARS
        if j < 0:
            sig[i] = 0
            continue
        slope = hma[i] - hma[j]
        floor = K * atr[i] * (SLOPE_BARS ** 0.5)
        if slope > floor:
            up_run += 1
            dn_run = 0
        elif slope < -floor:
            dn_run += 1
            up_run = 0
        else:
            up_run = 0
            dn_run = 0
        if up_run >= PERSIST:
            sig[i] = 1
        elif dn_run >= PERSIST:
            sig[i] = -1
        else:
            sig[i] = 0
    return sig


def main():
    d = load()
    by = day_indices(d["t"])
    sig = signal_series(d)
    label_dir = {}
    for day, dd in TREND_DAYS.items():
        label_dir[day] = 1 if dd == "up" else -1
    for day in CHOP_DAYS:
        label_dir[day] = 0

    per_day = {}
    for day in sorted(label_dir.keys()):
        idx = by.get(day, [])
        if not idx:
            continue
        want = label_dir[day]
        m = len(idx)
        correct = 0
        wrong = 0
        for i in idx:
            s = sig[i]
            if s == 0:
                continue
            if want != 0 and s == want:
                correct += 1
            else:
                wrong += 1
        per_day[day] = (correct - wrong) / m

    sep = score_separation(per_day)
    print("params: HMA_LEN=%d ATR_LEN=%d SLOPE_BARS=%d K=%.2f PERSIST=%d" % (HMA_LEN, ATR_LEN, SLOPE_BARS, K, PERSIST))
    print("lag_bars ~= HMA_group_delay + SLOPE_BARS + PERSIST")
    for day in sorted(per_day.keys()):
        tag = TREND_DAYS.get(day, "CHOP")
        print("%s %-5s score=% .3f" % (day, tag, per_day[day]))
    print("07-16 flagged DOWN:", per_day.get("2026-07-16", 0) > 0)
    if sep:
        print("trend_range", sep["trend_range"], "chop_range", sep["chop_range"])
        print("gap", sep["gap"], "clean", sep["clean_separation"])


if __name__ == "__main__":
    main()
