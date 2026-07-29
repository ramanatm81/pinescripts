from trenddet_common import load, day_indices, TREND_DAYS, CHOP_DAYS, score_separation

ATR_LEN = 14
K = 30
DISP_TH = 0.15
LAG = 0


def atr_series(h, l, c):
    n = len(c)
    tr = [0.0] * n
    for i in range(n):
        tr[i] = h[i] - l[i] if i == 0 else max(
            h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])
        )
    return tr


def run(K=K, DISP_TH=DISP_TH):
    d = load()
    t, c = d["t"], d["c"]
    h, l = d["h"], d["l"]
    n = d["n"]
    tr = atr_series(h, l, c)
    by = day_indices(t)

    sig = [0] * n
    for day, idxs in by.items():
        for j, i in enumerate(idxs):
            if j < K:
                sig[i] = 0
                continue
            anchor = c[idxs[j - K]]
            path = 0.0
            for m in range(j - K + 1, j + 1):
                path += tr[idxs[m]]
            if path <= 0:
                sig[i] = 0
                continue
            disp = (c[i] - anchor) / path
            if disp >= DISP_TH:
                sig[i] = 1
            elif disp <= -DISP_TH:
                sig[i] = -1
            else:
                sig[i] = 0

    day_metric = {}
    per_day = {}
    for day, idxs in by.items():
        if day not in TREND_DAYS and day not in CHOP_DAYS:
            continue
        want = 1 if TREND_DAYS.get(day) == "up" else (-1 if day in TREND_DAYS else None)
        tot = len(idxs)
        correct = sum(1 for i in idxs if sig[i] != 0 and sig[i] == want)
        wrong = sum(1 for i in idxs if sig[i] != 0 and sig[i] != want)
        m = (correct - wrong) / tot
        day_metric[day] = m
        per_day[day] = round(m, 4)

    return per_day, score_separation(day_metric), day_metric


if __name__ == "__main__":
    per_day, sep, dm = run()
    for day in sorted(per_day):
        lab = TREND_DAYS.get(day, "chop")
        print(f"{day} {str(lab):5s} {per_day[day]:+.4f}")
    print("gap", round(sep["gap"], 4), "clean", sep["clean_separation"])
    print("trend_range", sep["trend_range"])
    print("chop_range", sep["chop_range"])
    d716 = dm.get("2026-07-16")
    print("0716_down_flag", d716 is not None and d716 > 0, "val", round(d716, 4))
