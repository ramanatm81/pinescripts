"""Dynamic-N detector for slope_touch_fade, ported from live_trend.pine's window scan.

Instead of one fixed-N OLS per bar, scan N = win_min..win_max by win_step, compute OLS for each,
and pick the BEST-qualifying window (run >= run_min AND r2 >= min_r2, highest r2). That winning
window's slope-sign + run + r2 feed the SAME arm/pullback/lock machine as the fixed-N detect().

This is recompute-only (Pine never exported per-scan-window run/r2), so it's for the raw 5yr file.
Reuses port.ols() as the OLS primitive. detect_dynamic() mirrors detect()'s return shape
(long_sig, short_sig, fext_long, fext_short [, long_arm, short_arm]) so trade_loop is unchanged.
"""
import slope_touch_fade_bt as port


def detect_dynamic(bars, win_min=60, win_max=240, win_step=10, run_min=100.0, min_r2=0.75,
                   pullback=70.0, break_tol=5.0, sr_half=10, return_arms=False):
    high = [b[2] for b in bars]; low = [b[3] for b in bars]; close = [b[4] for b in bars]
    n = len(bars)

    have_pine_sr = any(b[6] is not None for b in bars)
    if have_pine_sr:
        res_line = [b[6] for b in bars]; supp_line = [b[7] for b in bars]
    else:
        res_line, supp_line = port.pivots(high, low, sr_half)

    epoch = [b[5] for b in bars]

    long_sig = [False] * n; short_sig = [False] * n
    fext_long = [None] * n; fext_short = [None] * n
    long_arm = [False] * n; short_arm = [False] * n

    sA = lA = False
    sE = lE = None
    lock_low = lock_high = None
    bars_since_gap = 0
    for i in range(n):
        gap_now = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        bars_since_gap = 1 if gap_now else bars_since_gap + 1
        if gap_now:
            sA = lA = False; sE = lE = None; lock_low = lock_high = None

        # --- WINDOW SCAN: pick the best-fitting qualifying N (live_trend's pickBest) ---
        best_sign = 0; best_r2 = -1.0; best_run = None
        # only scan windows that fit in the contiguous post-gap history
        wmax = min(win_max, bars_since_gap)
        N = win_min
        while N <= wmax:
            if i >= N - 1:
                s, r = port.ols(close, i, N)
                if s is not None and r is not None:
                    run = abs(s) * (N - 1)
                    if run >= run_min and r >= min_r2 and r > best_r2:
                        best_r2 = r; best_run = run; best_sign = 1 if s > 0 else -1
            N += win_step

        q = best_run is not None
        has_up, has_down = q and best_sign > 0, q and best_sign < 0

        rl, sl = res_line[i], supp_line[i]
        t_res = rl is not None and high[i] >= rl and close[i] <= rl + break_tol
        t_sup = sl is not None and low[i] <= sl and close[i] >= sl - break_tol
        if lock_high is not None and high[i] > lock_high:
            lock_high = None
        if lock_low is not None and low[i] < lock_low:
            lock_low = None

        # SHORT side (freeze-at-dot: sE stays at the arm bar's high)
        if not sA:
            if has_up and t_res and lock_high is None:
                sA, sE = True, high[i]; short_arm[i] = True
        else:
            if close[i] <= sE - pullback:
                short_sig[i] = True; fext_short[i] = sE
                lock_high, sA, sE = sE, False, None
        # LONG side
        if not lA:
            if has_down and t_sup and lock_low is None:
                lA, lE = True, low[i]; long_arm[i] = True
        else:
            if close[i] >= lE + pullback:
                long_sig[i] = True; fext_long[i] = lE
                lock_low, lA, lE = lE, False, None

    if return_arms:
        return long_sig, short_sig, fext_long, fext_short, long_arm, short_arm
    return long_sig, short_sig, fext_long, fext_short
