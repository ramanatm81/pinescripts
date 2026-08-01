"""Fully-numpy fast pipeline: convert bars ONCE, then detect+trade entirely in JIT with no
Python-list conversion between stages. This is the sweep engine — ~0.4s per config on 5yr.

fast_bars(bars) -> arrays (call once).  sim(arrays, cfg) -> (n_trades, net, wins, losses, gross_p,
gross_l) as a JIT tuple.  Validated to match slope_touch_fade_bt exactly (see validate_fast2.py).
"""
import numpy as np
from numba import njit
from fast_detect import _pivots, _detect_core


def fast_bars(bars):
    """One-time conversion of the port's bar tuples into numpy arrays."""
    n = len(bars)
    ctmin = np.empty(n, np.int32)
    o = np.empty(n); h = np.empty(n); l = np.empty(n); c = np.empty(n); ep = np.empty(n)
    for i in range(n):
        b = bars[i]
        ctmin[i] = b[0]; o[i] = b[1]; h[i] = b[2]; l[i] = b[3]; c[i] = b[4]; ep[i] = b[5]
    have_pine = any(b[6] is not None for b in bars)
    if have_pine:
        res = np.array([np.nan if b[6] is None else b[6] for b in bars])
        supp = np.array([np.nan if b[7] is None else b[7] for b in bars])
    else:
        res = supp = None
    return dict(ctmin=ctmin, o=o, h=h, l=l, c=c, ep=ep, res=res, supp=supp, have_pine=have_pine)


@njit(cache=True)
def _trade_loop(ctmin, high, low, close, epoch, long_sig, short_sig, fext_long, fext_short,
                block_ny, block_ln, enable_trail, trail, enable_init, stop_buf, mult):
    """Freeze-at-dot trade loop. Returns (n, net_pts, wins, losses, gross_profit, gross_loss).
    Mirrors slope_touch_fade_bt.trade_loop branch-for-branch."""
    n = close.shape[0]
    pos = 0
    entry_px = np.nan; init_stop = np.nan; best = np.nan
    ntr = 0; net = 0.0; wins = 0; losses = 0; gp = 0.0; gl = 0.0

    def record(direction, px, e_px):
        pts = (px - e_px) if direction > 0 else (e_px - px)
        return pts

    for i in range(n):
        cm = ctmin[i]
        gap_edge = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        session_flat = (900 <= cm < 960) or (block_ny and 510 <= cm < 540) \
            or (block_ln and 120 <= cm < 150) or gap_edge
        closed = False
        reversed_bar = False

        if pos > 0 and short_sig[i] and not session_flat:
            pts = close[i] - entry_px
            net += pts; ntr += 1
            if pts > 0: wins += 1; gp += pts
            else: losses += 1; gl += -pts
            pos = -1; entry_px = close[i]; best = low[i]
            init_stop = (fext_short[i] + stop_buf) if not np.isnan(fext_short[i]) else np.nan
            reversed_bar = True
        elif pos < 0 and long_sig[i] and not session_flat:
            pts = entry_px - close[i]
            net += pts; ntr += 1
            if pts > 0: wins += 1; gp += pts
            else: losses += 1; gl += -pts
            pos = 1; entry_px = close[i]; best = high[i]
            init_stop = (fext_long[i] - stop_buf) if not np.isnan(fext_long[i]) else np.nan
            reversed_bar = True

        if (not reversed_bar) and pos > 0 and (enable_trail or enable_init):
            if high[i] > best: best = high[i]
            sl = np.nan
            if enable_init: sl = init_stop
            if enable_trail:
                tt = best - trail
                sl = tt if np.isnan(sl) else max(sl, tt)
            if (not np.isnan(sl)) and low[i] <= sl:
                pts = sl - entry_px
                net += pts; ntr += 1
                if pts > 0: wins += 1; gp += pts
                else: losses += 1; gl += -pts
                pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        elif (not reversed_bar) and pos < 0 and (enable_trail or enable_init):
            if low[i] < best: best = low[i]
            sl = np.nan
            if enable_init: sl = init_stop
            if enable_trail:
                tt = best + trail
                sl = tt if np.isnan(sl) else min(sl, tt)
            if (not np.isnan(sl)) and high[i] >= sl:
                pts = entry_px - sl
                net += pts; ntr += 1
                if pts > 0: wins += 1; gp += pts
                else: losses += 1; gl += -pts
                pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True

        if session_flat and pos != 0:
            pts = (close[i] - entry_px) if pos > 0 else (entry_px - close[i])
            net += pts; ntr += 1
            if pts > 0: wins += 1; gp += pts
            else: losses += 1; gl += -pts
            pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True

        if pos == 0 and not session_flat and not closed and not reversed_bar:
            if long_sig[i] and not short_sig[i]:
                pos = 1; entry_px = close[i]; best = high[i]
                init_stop = (fext_long[i] - stop_buf) if not np.isnan(fext_long[i]) else np.nan
            elif short_sig[i] and not long_sig[i]:
                pos = -1; entry_px = close[i]; best = low[i]
                init_stop = (fext_short[i] + stop_buf) if not np.isnan(fext_short[i]) else np.nan

    if pos != 0:
        pts = (close[n - 1] - entry_px) if pos > 0 else (entry_px - close[n - 1])
        net += pts; ntr += 1
        if pts > 0: wins += 1; gp += pts
        else: losses += 1; gl += -pts
    return ntr, net, wins, losses, gp, gl


def sim(A, win_len=90, run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10,
        block_ny=True, block_ln=True, enable_trail=False, trail=80.0, enable_init=True,
        stop_buf=10.0, mult=2.0, sr_cache=None):
    """Full detect+trade for one config on pre-converted arrays A. Returns a stats dict."""
    if A["have_pine"]:
        res, supp = A["res"], A["supp"]
    elif sr_cache is not None:
        res, supp = sr_cache
    else:
        res, supp = _pivots(A["h"], A["l"], sr_half)
    ls, ss, fl, fs, la, sa = _detect_core(A["h"], A["l"], A["c"], A["ep"], res, supp,
                                          win_len, run_min, min_r2, pullback, break_tol)
    ntr, net, wins, losses, gp, gl = _trade_loop(
        A["ctmin"], A["h"], A["l"], A["c"], A["ep"], ls, ss, fl, fs,
        block_ny, block_ln, enable_trail, trail, enable_init, stop_buf, mult)
    pf = (gp / gl) if gl > 0 else float("inf")
    return dict(n=ntr, net=net, usd=net * mult, wins=wins, losses=losses,
                wr=100.0 * wins / ntr if ntr else 0.0, pf=pf, avg=net / ntr if ntr else 0.0)
