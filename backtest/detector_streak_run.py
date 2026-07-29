from trenddet_common import load, day_indices, TREND_DAYS, CHOP_DAYS, score_separation

L = 7
SMOOTH = 3
STREAK_TH = 2


def med3(x):
    out = list(x)
    for i in range(2, len(x)):
        out[i] = sorted(x[i - 2:i + 1])[1]
    return out


def run_detector(o, h, l, c):
    n = len(c)
    hs = med3(h)
    ls = med3(l)

    sig = [0] * n

    last_piv_high = None
    last_piv_low = None
    up_streak = 0
    down_streak = 0

    for i in range(n):
        if i >= 2 * L:
            j = i - L
            hw = hs[j - L:j + L + 1]
            lw = ls[j - L:j + L + 1]
            if hs[j] == max(hw):
                if last_piv_high is not None:
                    if hs[j] < last_piv_high:
                        down_streak += 1
                        up_streak = 0
                    elif hs[j] > last_piv_high:
                        up_streak += 1
                        down_streak = 0
                last_piv_high = hs[j]
            if ls[j] == min(lw):
                if last_piv_low is not None:
                    if ls[j] < last_piv_low:
                        down_streak += 1
                        up_streak = 0
                    elif ls[j] > last_piv_low:
                        up_streak += 1
                        down_streak = 0
                last_piv_low = ls[j]

        if down_streak >= STREAK_TH:
            sig[i] = -1
        elif up_streak >= STREAK_TH:
            sig[i] = 1
        else:
            sig[i] = 0
    return sig


def main():
    d = load()
    o, h, l, c, t = d["o"], d["h"], d["l"], d["c"], d["t"]
    sig = run_detector(o, h, l, c)
    by = day_indices(t)

    per_day = {}
    for day in sorted(list(TREND_DAYS.keys()) + list(CHOP_DAYS)):
        if day not in by:
            continue
        idx = by[day]
        want = 0
        if day in TREND_DAYS:
            want = -1 if TREND_DAYS[day] == "down" else 1
        correct = wrong = 0
        for i in idx:
            if sig[i] == 0:
                continue
            if want != 0 and sig[i] == want:
                correct += 1
            else:
                wrong += 1
        m = (correct - wrong) / len(idx)
        per_day[day] = m

    sep = score_separation(per_day)
    for day in sorted(per_day):
        lab = TREND_DAYS.get(day, "chop")
        print(f"{day} {lab:>5} {per_day[day]:+.3f}")
    print("SEP", sep)
    print("0716 fires down:", per_day.get("2026-07-16", 0) > 0)
    return per_day, sep


if __name__ == "__main__":
    main()
