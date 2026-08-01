"""Port of nq_regime.pine's regime classifier to Python (for offline N-vs-regime testing).

Method (from nq_regime.pine + docs/regime_detection_research.md), all causal:
  - Judge on 1-HOUR bars (1m futures ~ random walk; regime only detectable on ~1h).
  - R2 of linear fit close~bar_index over r2_len HTF bars; slope sign from linreg 1-bar diff.
  - DIRECTIONAL if R2 >= r2_trend (default 0.20 for N=20), else MEAN-REVERSION.
  - Optional Volatility-Switch vote (falling vol -> trend mode). Default matches Pine useVolVote.
Returns a per-1m-bar regime label by forward-filling the CONFIRMED prior 1h bar (no lookahead).
"""
import math
from datetime import datetime, timezone, timedelta

CT = timezone(timedelta(hours=-5))


def _r2_slope(close_win):
    """R^2 of close vs index, and slope sign, over a window (list oldest..newest)."""
    N = len(close_win)
    if N < 3:
        return None, 0
    xs = list(range(N))
    mx = sum(xs) / N
    my = sum(close_win) / N
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in close_win)
    sxy = sum((xs[k] - mx) * (close_win[k] - my) for k in range(N))
    if sxx <= 0 or syy <= 0:
        return 0.0, 0
    r = sxy / (sxx * syy) ** 0.5
    slope = sxy / sxx
    return r * r, (1 if slope > 0 else -1)


def resample_1h(bars):
    """Aggregate 1m bars -> 1h OHLC keyed by CT hour bucket. bars are the port's tuples
    (ctmin, o, h, l, c, epoch, ...). Returns list of (h_epoch, o, h, l, c) per 1h bucket."""
    out = []
    cur_key = None
    o = h = l = c = None
    ep = None
    for b in bars:
        epoch = b[5]
        key = int(epoch // 3600)          # hour bucket
        if key != cur_key:
            if cur_key is not None:
                out.append((ep, o, h, l, c))
            cur_key = key
            o = b[1]; h = b[2]; l = b[3]; c = b[4]; ep = epoch
        else:
            h = max(h, b[2]); l = min(l, b[3]); c = b[4]
    if cur_key is not None:
        out.append((ep, o, h, l, c))
    return out


def regime_per_bar(bars, r2_len=20, r2_trend=0.20, use_vol_vote=True, vol_len=20):
    """Return a list len(bars) of regime labels: +1 directional-up, -1 directional-down,
    0 mean-reversion. Computed on 1h bars (confirmed prior bar) then forward-filled to 1m."""
    h1 = resample_1h(bars)
    n1 = len(h1)
    closes = [x[4] for x in h1]
    # volatility switch: normalized stdev of returns; rising vol -> mean-revert (vote against trend)
    rets = [0.0] + [closes[i] - closes[i - 1] for i in range(1, n1)]
    labels_1h = [0] * n1
    for i in range(n1):
        if i < r2_len - 1:
            labels_1h[i] = 0
            continue
        win = closes[i - r2_len + 1:i + 1]
        r2, slope_sign = _r2_slope(win)
        directional = r2 is not None and r2 >= r2_trend
        if use_vol_vote and directional and i >= vol_len:
            recent = [abs(x) for x in rets[i - vol_len + 1:i + 1]]
            older = [abs(x) for x in rets[max(0, i - 2 * vol_len + 1):i - vol_len + 1]]
            if older and sum(recent) / len(recent) > sum(older) / len(older):
                directional = False        # rising vol -> mean-reversion vote
        labels_1h[i] = slope_sign if directional else 0

    # map each 1m bar to the CONFIRMED PRIOR 1h bar's label (no lookahead): use bucket-1
    h1_epoch = [x[0] for x in h1]
    label_by_key = {}
    for i in range(n1):
        label_by_key[int(h1_epoch[i] // 3600)] = labels_1h[i]
    keys_sorted = sorted(label_by_key.keys())
    # prior-bar label for a given hour key = label of the previous 1h bucket
    prior_label = {}
    for j, k in enumerate(keys_sorted):
        prior_label[k] = label_by_key[keys_sorted[j - 1]] if j > 0 else 0

    out = []
    for b in bars:
        out.append(prior_label.get(int(b[5] // 3600), 0))
    return out
