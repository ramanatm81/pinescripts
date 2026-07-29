import csv

OOS_PATH = "/Users/maheshk81/Downloads/data.csv"
FIVEYR_PATH = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

TREND_DAYS = {
    "2026-07-07": "down",
    "2026-07-09": "up",
    "2026-07-13": "down",
    "2026-07-16": "down",
    "2026-07-21": "up",
    "2026-07-24": "down",
}
CHOP_DAYS = {"2026-07-06", "2026-07-08", "2026-07-15", "2026-07-20"}


def load(path=OOS_PATH):
    o = []
    h = []
    l = []
    c = []
    t = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            try:
                o.append(float(r["open"]))
                h.append(float(r["high"]))
                l.append(float(r["low"]))
                c.append(float(r["close"]))
                t.append(r["time"])
            except (ValueError, KeyError):
                continue
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "n": len(c)}


def day_indices(t):
    by = {}
    for i, ts in enumerate(t):
        by.setdefault(ts[:10], []).append(i)
    return by


def score_separation(day_metric):
    tr = [day_metric[d] for d in TREND_DAYS if d in day_metric]
    ch = [day_metric[d] for d in CHOP_DAYS if d in day_metric]
    if not tr or not ch:
        return None
    tr_min, tr_max = min(tr), max(tr)
    ch_min, ch_max = min(ch), max(ch)
    gap = tr_min - ch_max
    return {
        "trend_range": (tr_min, tr_max),
        "chop_range": (ch_min, ch_max),
        "gap": gap,
        "clean_separation": gap > 0,
    }
