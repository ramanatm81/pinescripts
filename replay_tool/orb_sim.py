#!/usr/bin/env python3
"""Fast numba simulation engine for opening_range_breakout ("Sapporo"), for the UI's "New Run".

Mirrors backtest/orb_bt.py (the validated port -- itself bar-exact vs the TradingView trade list)
branch-for-branch: OR accumulation over the first or_minutes after 08:30 CT, break on first CLOSE
beyond OR edge +/- buffer, one trade/day/side, exit modes {0 trail, 1 fixed, 2 OR-mult, 3 EOD-hold},
and an independent CATASTROPHIC stop at cat_mult * trailing daily-ATR.

The daily ATR is dict/date-based (numba can't build it), so it is precomputed ONCE in Python as a
per-bar array (the entry-day ATR carried on every bar) and passed into the JIT core -- the
"precompute then JIT, no per-bar Python" rule from backtest/PERF_NOTES.md. verify() asserts the numba
trade list equals orb_bt.run() -- the methodology's oracle gate.
"""
import os
import sys
import numpy as np
from numba import njit
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))
import orb_bt as port  # the validated oracle

_EXIT_CODE = {0: None, 1: "cat", 2: "stop", 3: "tp", 4: "trail", 5: "session", 6: "open"}

_BARS_CACHE = {}


def _ct_iso(epoch_sec):
    return datetime.fromtimestamp(epoch_sec, port.CT).isoformat()


def load_bars(dataset):
    if dataset in _BARS_CACHE:
        return _BARS_CACHE[dataset]
    path = port.OOS if dataset == "oos" else port.FIVE_YR
    bars = port.load(path)
    n = len(bars)
    cm = np.empty(n, np.int32); o = np.empty(n); h = np.empty(n)
    lo = np.empty(n); c = np.empty(n); ep = np.empty(n)
    for i, b in enumerate(bars):
        cm[i] = b[0]; o[i] = b[1]; h[i] = b[2]; lo[i] = b[3]; c[i] = b[4]; ep[i] = b[5]
    iso = np.array([_ct_iso(e) for e in ep])
    # per-bar trailing daily-ATR keyed by the bar's own CT date (past-only). Computed once here;
    # the core reads atr_bar[entry_i] at entry so the cat stop uses the entry-day ATR, exactly like
    # orb_bt.run() which does atr.get(entry_date). NaN until atr_days full prior days exist.
    dates = np.array([datetime.fromtimestamp(e, port.CT).date().toordinal() for e in ep], np.int64)
    arr = dict(cm=cm, o=o, h=h, l=lo, c=c, ep=ep, iso=iso, dates=dates, path=path, n=n)
    _BARS_CACHE[dataset] = arr
    return arr


def _atr_per_bar(dates, h, l, ndays):
    """Trailing avg of prior-day full ranges, as a per-bar array (each bar carries its own day's
    ATR = mean of the ndays days strictly before it). Matches orb_bt._daily_atr exactly."""
    n = len(dates)
    day_hi = {}; day_lo = {}; order = []
    for i in range(n):
        d = dates[i]
        if d not in day_hi:
            day_hi[d] = h[i]; day_lo[d] = l[i]; order.append(d)
        else:
            if h[i] > day_hi[d]: day_hi[d] = h[i]
            if l[i] < day_lo[d]: day_lo[d] = l[i]
    rng = {d: day_hi[d] - day_lo[d] for d in order}
    atr_of_day = {}
    for k, d in enumerate(order):
        prev = order[max(0, k - ndays):k]
        atr_of_day[d] = (sum(rng[p] for p in prev) / len(prev)) if len(prev) >= ndays else np.nan
    out = np.empty(n)
    for i in range(n):
        out[i] = atr_of_day[dates[i]]
    return out


def slice_bars(dataset, start=None, end=None, lead=90):
    a = load_bars(dataset)
    iso = a["iso"]; n = a["n"]
    lo_i = 0
    if start:
        while lo_i < n and iso[lo_i][:len(start)] < start:
            lo_i += 1
    hi_i = n
    if end:
        j = 0
        while j < n and iso[j][:len(end)] <= end:
            j += 1
        hi_i = j
    if lo_i >= hi_i:
        raise ValueError(f"empty range: start={start} end={end}")
    warm = max(0, lo_i - lead)
    sl = slice(warm, hi_i)
    out = dict(cm=a["cm"][sl].copy(), o=a["o"][sl].copy(), h=a["h"][sl].copy(),
               l=a["l"][sl].copy(), c=a["c"][sl].copy(), ep=a["ep"][sl].copy(),
               dates=a["dates"][sl].copy(), iso=a["iso"][sl], path=a["path"], n=hi_i - warm)
    rec_start = lo_i - warm
    return out, rec_start


@njit(cache=True)
def _core(cm, o, h, l, c, ep, atr_bar, or_minutes, break_end_min, break_buf, or_min_pts,
          use_slope, slope_len, slope_min, exit_mode, trail_pts, tp_pts, sl_pts,
          tp_mult, sl_mult, use_cat, cat_mult, enable_long, enable_short, rec_start):
    n = c.shape[0]
    pos = np.zeros(n, np.int8)
    entry_px = np.full(n, np.nan)
    orh_arr = np.full(n, np.nan); orl_arr = np.full(n, np.nan)
    stop_arr = np.full(n, np.nan)
    cum = np.zeros(n)
    unreal = np.full(n, np.nan)
    entry_dir = np.zeros(n, np.int8)
    exit_code = np.zeros(n, np.int8)
    exit_px_arr = np.full(n, np.nan)
    t_dir = np.zeros(n, np.int8); t_ei = np.zeros(n, np.int64); t_xi = np.zeros(n, np.int64)
    t_ep = np.zeros(n); t_xp = np.zeros(n); t_pts = np.zeros(n); t_code = np.zeros(n, np.int8)
    m = 0

    orH = np.nan; orL = np.nan; or_ready = False
    took_long = False; took_short = False
    p = 0; e_px = np.nan; e_i = -1; best = np.nan
    init_stop = np.nan; tp_level = np.nan; cat_stop = np.nan
    cum_v = 0.0
    prev_min_since = -10000

    for i in range(n):
        min_since = cm[i] - 510
        gap = i > 0 and (ep[i] - ep[i - 1]) / 60.0 > 60
        eod = 900 <= cm[i] < 960
        new_day = (min_since == 0) or (prev_min_since < 0 and min_since >= 0) or gap
        if new_day:
            orH = np.nan; orL = np.nan; or_ready = False
            took_long = False; took_short = False

        in_or = 0 <= min_since < or_minutes
        in_break = or_minutes <= min_since < break_end_min
        if in_or:
            orH = h[i] if np.isnan(orH) else max(orH, h[i])
            orL = l[i] if np.isnan(orL) else min(orL, l[i])
        if min_since >= or_minutes and not or_ready and not np.isnan(orH):
            or_ready = True
        or_width = np.nan if (np.isnan(orH) or np.isnan(orL)) else orH - orL
        orh_arr[i] = orH; orl_arr[i] = orL

        slope = (c[i] - c[i - slope_len]) / slope_len if i >= slope_len else 0.0

        xcode = 0; xpx = np.nan
        # manage: cat stop first (binds if tighter / alone in EOD-hold), then mode stop/tp
        if p != 0:
            if (not np.isnan(cat_stop)):
                if p > 0 and l[i] <= cat_stop:
                    xpx = cat_stop; xcode = 1
                elif p < 0 and h[i] >= cat_stop:
                    xpx = cat_stop; xcode = 1
            if xcode == 0 and exit_mode == 0:
                st = best - trail_pts if p > 0 else best + trail_pts
                if p > 0 and l[i] <= st:
                    xpx = st; xcode = 4
                elif p < 0 and h[i] >= st:
                    xpx = st; xcode = 4
            elif xcode == 0 and (exit_mode == 1 or exit_mode == 2):
                if p > 0:
                    if l[i] <= init_stop:
                        xpx = init_stop; xcode = 2
                    elif h[i] >= tp_level:
                        xpx = tp_level; xcode = 3
                else:
                    if h[i] >= init_stop:
                        xpx = init_stop; xcode = 2
                    elif l[i] <= tp_level:
                        xpx = tp_level; xcode = 3

        if xcode != 0:
            pts = (xpx - e_px) if p > 0 else (e_px - xpx)
            cum_v += pts * 2.0
            t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = i; t_ep[m] = e_px
            t_xp[m] = xpx; t_pts[m] = pts; t_code[m] = xcode; m += 1
            exit_code[i] = xcode; exit_px_arr[i] = xpx
            p = 0; e_px = np.nan; e_i = -1
            cat_stop = np.nan; init_stop = np.nan; tp_level = np.nan
        else:
            if p != 0:
                best = max(best, h[i]) if p > 0 else min(best, l[i])

        # EOD / gap flatten
        if p != 0 and (eod or gap):
            xpx = c[i]
            pts = (xpx - e_px) if p > 0 else (e_px - xpx)
            cum_v += pts * 2.0
            t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = i; t_ep[m] = e_px
            t_xp[m] = xpx; t_pts[m] = pts; t_code[m] = 5; m += 1
            exit_code[i] = 5; exit_px_arr[i] = xpx
            p = 0; e_px = np.nan; e_i = -1
            cat_stop = np.nan; init_stop = np.nan; tp_level = np.nan

        # entries (flat only, and only in the recorded range so warm-up bars fill OR/ATR but no trade)
        if p == 0 and i >= rec_start:
            or_size_ok = or_min_pts <= 0.0 or ((not np.isnan(or_width)) and or_width >= or_min_pts)
            long_break = (or_ready and in_break and enable_long and not took_long and or_size_ok
                          and not np.isnan(orH) and c[i] > orH + break_buf
                          and ((not use_slope) or slope >= slope_min))
            short_break = (or_ready and in_break and enable_short and not took_short and or_size_ok
                           and not np.isnan(orL) and c[i] < orL - break_buf
                           and ((not use_slope) or slope <= -slope_min))
            a_atr = atr_bar[i]
            if long_break:
                p = 1; e_px = c[i]; e_i = i; best = h[i]; took_long = True; entry_dir[i] = 1
                if exit_mode == 1:
                    init_stop = c[i] - sl_pts; tp_level = c[i] + tp_pts
                elif exit_mode == 2:
                    init_stop = orL - sl_mult * or_width; tp_level = c[i] + tp_mult * or_width
                cat_stop = (c[i] - cat_mult * a_atr) if (use_cat and not np.isnan(a_atr)) else np.nan
            elif short_break:
                p = -1; e_px = c[i]; e_i = i; best = l[i]; took_short = True; entry_dir[i] = -1
                if exit_mode == 1:
                    init_stop = c[i] + sl_pts; tp_level = c[i] - tp_pts
                elif exit_mode == 2:
                    init_stop = orH + sl_mult * or_width; tp_level = c[i] - tp_mult * or_width
                cat_stop = (c[i] + cat_mult * a_atr) if (use_cat and not np.isnan(a_atr)) else np.nan

        pos[i] = p
        entry_px[i] = e_px if p != 0 else np.nan
        if p > 0:
            stop_arr[i] = cat_stop if (exit_mode == 3 or exit_mode == 0 and np.isnan(init_stop)) else init_stop
        elif p < 0:
            stop_arr[i] = cat_stop if (exit_mode == 3 or exit_mode == 0 and np.isnan(init_stop)) else init_stop
        cum[i] = cum_v
        if p != 0:
            unreal[i] = ((c[i] - e_px) if p > 0 else (e_px - c[i])) * 2.0
        prev_min_since = min_since

    open_i = -1
    if p != 0:
        pts = (c[n - 1] - e_px) if p > 0 else (e_px - c[n - 1])
        cum_v += pts * 2.0
        t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = n - 1; t_ep[m] = e_px
        t_xp[m] = c[n - 1]; t_pts[m] = pts; t_code[m] = 6; m += 1
        exit_code[n - 1] = 6; exit_px_arr[n - 1] = c[n - 1]
        cum[n - 1] = cum_v
        open_i = n - 1

    return (pos, entry_px, orh_arr, orl_arr, stop_arr, cum, unreal, entry_dir,
            exit_code, exit_px_arr,
            t_dir[:m], t_ei[:m], t_xi[:m], t_ep[:m], t_xp[:m], t_pts[:m], t_code[:m], open_i)


def build_run(dataset, cfg, start=None, end=None):
    lead = max(int(cfg["break_end_min"]) + 5, 120)
    a, rec_start = slice_bars(dataset, start, end, lead=lead)
    cm, o, h, l, c, ep = a["cm"], a["o"], a["h"], a["l"], a["c"], a["ep"]
    atr_bar = _atr_per_bar(a["dates"], h, l, int(cfg["atr_days"])) if cfg["use_cat"] \
        else np.full(len(c), np.nan)
    (pos, entry_px, orh, orl, stop_lvl, cum, unreal, entry_dir, exit_code, exit_px,
     t_dir, t_ei, t_xi, t_ep, t_xp, t_pts, t_code, open_i) = _core(
        cm, o, h, l, c, ep, atr_bar, int(cfg["or_minutes"]), int(cfg["break_end_min"]),
        cfg["break_buf"], cfg["or_min_pts"], cfg["use_slope"], int(cfg["slope_len"]),
        cfg["slope_min"], int(cfg["exit_mode"]), cfg["trail_pts"], cfg["tp_pts"], cfg["sl_pts"],
        cfg["tp_mult"], cfg["sl_mult"], cfg["use_cat"], cfg["cat_mult"],
        cfg["enable_long"], cfg["enable_short"], rec_start)
    n = c.shape[0]

    def ri(i):
        return int(i) - rec_start

    trades = []
    cum_running = 0.0
    for k in range(len(t_dir)):
        d = int(t_dir[k]); ei = int(t_ei[k]); xi = int(t_xi[k])
        if ei < rec_start:
            continue
        epx = float(t_ep[k]); xpx = float(t_xp[k]); pts = float(t_pts[k])
        usd = pts * 2.0; cum_running += usd
        seg_hi = float(h[ei:xi + 1].max()); seg_lo = float(l[ei:xi + 1].min())
        if d > 0:
            mfe = seg_hi - epx; mae = seg_lo - epx
        else:
            mfe = epx - seg_lo; mae = epx - seg_hi
        reason = _EXIT_CODE.get(int(t_code[k]), "?")
        trades.append(dict(dir=d, entry_i=ri(ei), entry_time=_ct_iso(ep[ei]), entry_px=epx,
                           exit_i=ri(xi), exit_time=_ct_iso(ep[xi]), exit_px=xpx, pts=pts, usd=usd,
                           reason=reason, bars_held=xi - ei, cum_usd=cum_running,
                           mfe=mfe, mae=mae, mfe_usd=mfe * 2.0, mae_usd=mae * 2.0))

    base_cum = float(cum[rec_start - 1]) if rec_start > 0 else 0.0
    frames = []
    for i in range(rec_start, n):
        ecode = int(exit_code[i])
        ev_exit = (_EXIT_CODE[ecode], float(exit_px[i])) if ecode != 0 else None
        ed = int(entry_dir[i])
        ev_entry = (ed, float(entry_px[i])) if ed != 0 else None
        frames.append(dict(
            i=ri(i), time=_ct_iso(ep[i]), o=float(o[i]), h=float(h[i]), l=float(l[i]), c=float(c[i]),
            res=(None if np.isnan(orh[i]) else float(orh[i])),
            supp=(None if np.isnan(orl[i]) else float(orl[i])),
            run=None, r2=None, long_sig=False, short_sig=False, long_arm=False, short_arm=False,
            entry=ev_entry, exit=ev_exit, pos=int(pos[i]),
            entry_px=(None if pos[i] == 0 else float(entry_px[i])),
            stop_level=(None if np.isnan(stop_lvl[i]) else float(stop_lvl[i])),
            stop_kind=None, cum_usd=float(cum[i]) - base_cum,
            unreal_usd=(None if np.isnan(unreal[i]) else float(unreal[i]))))

    net = sum(t["pts"] for t in trades)
    wins = sum(1 for t in trades if t["pts"] > 0)
    nt = len(trades)
    gl = -sum(t["pts"] for t in trades if t["pts"] <= 0)
    gp = sum(t["pts"] for t in trades if t["pts"] > 0)
    st = dict(n=nt, net=net, usd=net * 2.0, wins=wins, losses=nt - wins,
              wr=100.0 * wins / nt if nt else 0.0, pf=(gp / gl) if gl > 0 else float("inf"),
              avg=net / nt if nt else 0.0)
    meta_cfg = dict(strategy="opening_range_breakout", **{k: cfg[k] for k in cfg}, mult=2.0)
    meta = dict(file=a["path"], tag=None, n_bars=len(frames), cfg=meta_cfg, stats=st, exact=False,
                start=start, end=end)
    return frames, trades, meta


def verify(dataset, cfg):
    """Assert the numba trade list equals the pure-Python port -- the oracle gate."""
    a = load_bars(dataset)
    bars = [(int(a["cm"][i]), float(a["o"][i]), float(a["h"][i]), float(a["l"][i]),
             float(a["c"][i]), float(a["ep"][i])) for i in range(a["n"])]
    ref = port.run(bars, or_minutes=int(cfg["or_minutes"]), break_end_min=int(cfg["break_end_min"]),
                   break_buf=cfg["break_buf"], or_min_pts=cfg["or_min_pts"],
                   use_slope=cfg["use_slope"], slope_len=int(cfg["slope_len"]),
                   slope_min=cfg["slope_min"], exit_mode=int(cfg["exit_mode"]),
                   trail_pts=cfg["trail_pts"], tp_pts=cfg["tp_pts"], sl_pts=cfg["sl_pts"],
                   tp_mult=cfg["tp_mult"], sl_mult=cfg["sl_mult"], use_cat=cfg["use_cat"],
                   cat_mult=cfg["cat_mult"], atr_days=int(cfg["atr_days"]),
                   enable_long=cfg["enable_long"], enable_short=cfg["enable_short"])
    _, trades, _ = build_run(dataset, cfg)
    got = [t["pts"] for t in trades]
    if len(ref) != len(got):
        return False, f"count mismatch: port={len(ref)} sim={len(got)}"
    for k, (rp, gp) in enumerate(zip([r[3] for r in ref], got)):
        if abs(rp - gp) > 1e-6:
            return False, f"trade #{k} pts mismatch: port={rp} sim={gp}"
    return True, f"exact match on {len(ref)} trades"


DEFAULT_CFG = dict(or_minutes=30, break_end_min=120, break_buf=3.0, or_min_pts=0.0,
                   use_slope=False, slope_len=15, slope_min=1.0, exit_mode=3,
                   trail_pts=150.0, tp_pts=120.0, sl_pts=80.0, tp_mult=1.0, sl_mult=1.0,
                   use_cat=True, cat_mult=1.5, atr_days=14, enable_long=True, enable_short=True)


if __name__ == "__main__":
    import argparse, time
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="oos", choices=["oos", "5yr"])
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    cfg = dict(DEFAULT_CFG)
    t0 = time.time()
    if a.verify:
        ok, msg = verify(a.dataset, cfg)
        print(f"VERIFY {a.dataset}: {'OK' if ok else 'FAIL'} -- {msg}  ({time.time()-t0:.1f}s)")
    else:
        frames, trades, meta = build_run(a.dataset, cfg)
        print(f"{a.dataset}: trades={meta['stats']['n']} net=${meta['stats']['usd']:.0f} "
              f"PF={meta['stats']['pf']:.2f}  ({time.time()-t0:.1f}s)")
