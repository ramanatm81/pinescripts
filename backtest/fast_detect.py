"""Numba-JIT fast detector for slope_touch_fade — mirrors slope_touch_fade_bt.detect() EXACTLY
(freeze-at-dot logic), but ~250x faster. Validated against the pure-Python port as the oracle.

Only the 5yr RECOMPUTE path is JIT'd (raw CSV, no Pine S/R/ols columns) — that's the slow one used
for sweeps. The OOS bar-exact path (Pine columns present) still uses the reference port.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def _pivots(high, low, half):
    n = high.shape[0]
    res = np.full(n, np.nan)
    supp = np.full(n, np.nan)
    last_hi = np.nan
    last_lo = np.nan
    for i in range(n):
        c = i - half
        if c - half >= 0 and c + half < n and c >= 0:
            ishi = True
            islo = True
            for j in range(c - half, c + half + 1):
                if high[c] < high[j]:
                    ishi = False
                if low[c] > low[j]:
                    islo = False
            if ishi:
                last_hi = high[c]
            if islo:
                last_lo = low[c]
        res[i] = last_hi
        supp[i] = last_lo
    return res, supp


@njit(cache=True)
def _detect_core(high, low, close, epoch, res_line, supp_line,
                 win_len, run_min, min_r2, pullback, break_tol):
    """Freeze-at-dot detector. Returns long_sig, short_sig, fext_long, fext_short, long_arm,
    short_arm (all length n). OLS run/r2 recomputed with a rolling window; sign from slope.
    Mirrors detect() branch-for-branch."""
    n = close.shape[0]
    long_sig = np.zeros(n, np.bool_)
    short_sig = np.zeros(n, np.bool_)
    fext_long = np.full(n, np.nan)
    fext_short = np.full(n, np.nan)
    long_arm = np.zeros(n, np.bool_)
    short_arm = np.zeros(n, np.bool_)

    sA = False
    lA = False
    sE = np.nan
    lE = np.nan
    lock_low = np.nan
    lock_high = np.nan
    bars_since_gap = 0
    fN = float(win_len)

    for i in range(n):
        gap_now = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        bars_since_gap = 1 if gap_now else bars_since_gap + 1
        window_clean = bars_since_gap >= win_len
        if gap_now:
            sA = False; lA = False; sE = np.nan; lE = np.nan
            lock_low = np.nan; lock_high = np.nan

        # rolling OLS over [i-win_len+1 .. i] of close vs k=0..N-1, centered on yref
        has_up = False
        has_down = False
        if window_clean and i >= win_len - 1:
            yref = close[i - (win_len - 1)]
            sx = 0.0; sy = 0.0; sxx = 0.0; syy = 0.0; sxy = 0.0
            for k in range(win_len):
                x = float(k)
                y = close[i - (win_len - 1) + k] - yref
                sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y
            vX = sxx - sx * sx / fN
            vY = syy - sy * sy / fN
            cXY = sxy - sx * sy / fN
            if vX > 0 and vY > 0:
                slope = cXY / vX
                r2 = cXY * cXY / (vX * vY)
                run = abs(slope) * (win_len - 1)
                if r2 >= min_r2 and run >= run_min:
                    if slope > 0:
                        has_up = True
                    elif slope < 0:
                        has_down = True

        rl = res_line[i]
        sl = supp_line[i]
        t_res = (not np.isnan(rl)) and high[i] >= rl and close[i] <= rl + break_tol
        t_sup = (not np.isnan(sl)) and low[i] <= sl and close[i] >= sl - break_tol
        if (not np.isnan(lock_high)) and high[i] > lock_high:
            lock_high = np.nan
        if (not np.isnan(lock_low)) and low[i] < lock_low:
            lock_low = np.nan

        # SHORT side (freeze at dot)
        if not sA:
            if has_up and t_res and np.isnan(lock_high):
                sA = True; sE = high[i]; short_arm[i] = True
        else:
            if close[i] <= sE - pullback:
                short_sig[i] = True; fext_short[i] = sE
                lock_high = sE; sA = False; sE = np.nan
        # LONG side
        if not lA:
            if has_down and t_sup and np.isnan(lock_low):
                lA = True; lE = low[i]; long_arm[i] = True
        else:
            if close[i] >= lE + pullback:
                long_sig[i] = True; fext_long[i] = lE
                lock_low = lE; lA = False; lE = np.nan

    return long_sig, short_sig, fext_long, fext_short, long_arm, short_arm


def detect_fast(bars, win_len=150, run_min=100.0, min_r2=0.75, pullback=70.0,
                break_tol=5.0, sr_half=10, return_arms=False):
    """Drop-in fast replacement for port.detect() on the RECOMPUTE path. Converts the bars tuples
    to numpy arrays once, then runs the JIT core."""
    n = len(bars)
    high = np.empty(n); low = np.empty(n); close = np.empty(n); epoch = np.empty(n)
    for i in range(n):
        b = bars[i]
        high[i] = b[2]; low[i] = b[3]; close[i] = b[4]; epoch[i] = b[5]

    have_pine_sr = any(b[6] is not None for b in bars)
    if have_pine_sr:
        res_line = np.array([np.nan if b[6] is None else b[6] for b in bars])
        supp_line = np.array([np.nan if b[7] is None else b[7] for b in bars])
    else:
        res_line, supp_line = _pivots(high, low, sr_half)

    ls, ss, fl, fs, la, sa = _detect_core(
        high, low, close, epoch, res_line, supp_line,
        win_len, run_min, min_r2, pullback, break_tol)

    # convert back to the port's list shapes (None for nan fext) so trade_loop is unchanged
    ls = ls.tolist(); ss = ss.tolist()
    fl = [None if np.isnan(x) else x for x in fl]
    fs = [None if np.isnan(x) else x for x in fs]
    if return_arms:
        return ls, ss, fl, fs, la.tolist(), sa.tolist()
    return ls, ss, fl, fs
