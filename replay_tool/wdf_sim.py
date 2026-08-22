#!/usr/bin/env python3
"""Fast numba simulation engine for window_displacement_fade, for the UI's "New Run" feature.

Mirrors backtest/window_displacement_fade_bt.py (the validated port) branch-for-branch:
  same-bar entry on close, anchor resets on trade CLOSE / session / first bar (NOT entry),
  prev-window pullback filter (allow long iff prevMv>prevThr, short iff prevMv<-prevThr),
  optional block-next-after-TP gated by the leg R2 the bar before the close-reset, fixed tp/sl.

Numba can't build Python dicts, so _core() returns parallel numpy arrays; build_run() adapts those
into the frames/trades dict shapes replay_tool/frames_export.write_parquet expects. verify() asserts
the trade tuples equal window_displacement_fade_bt.run() -- the methodology's oracle gate.

Bars are cached in-process (load_bars) so the CSV parse is paid once; a generate is then ~1-2s.
"""
import os
import sys
import numpy as np
from numba import njit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))
import window_displacement_fade_bt as port  # the validated oracle

_EXIT_CODE = {0: None, 1: "tp", 2: "stop", 3: "session", 4: "open"}

_BARS_CACHE = {}


def load_bars(dataset):
    """dataset in {'5yr','oos'}. Returns numpy arrays (cm,o,h,l,c,ep) + iso[] CT time strings, parsed
    via the port's loader (Chicago-normalized). Cached per dataset in-process."""
    if dataset in _BARS_CACHE:
        return _BARS_CACHE[dataset]
    path = port.OOS if dataset == "oos" else port.FIVE_YR
    bars = port.load(path)
    n = len(bars)
    cm = np.empty(n, np.int32); o = np.empty(n); h = np.empty(n)
    lo = np.empty(n); c = np.empty(n); ep = np.empty(n)
    for i, b in enumerate(bars):
        cm[i] = b[0]; o[i] = b[1]; h[i] = b[2]; lo[i] = b[3]; c[i] = b[4]; ep[i] = b[5]
    iso = np.array([_ct_iso(e) for e in ep])   # CT ISO per bar, for date-range slicing
    arr = dict(cm=cm, o=o, h=h, l=lo, c=c, ep=ep, iso=iso, path=path, n=n)
    _BARS_CACHE[dataset] = arr
    return arr


def slice_bars(dataset, start=None, end=None, lead=90):
    """Slice the dataset to CT-date range [start, end] (ISO prefixes like '2024-01', inclusive).
    Returns (arrays_dict, rec_start) where rec_start is the index (into the SLICED arrays) of the
    first bar to RECORD/TRADE. Up to `lead` bars before `start` are included as warm-up so the
    anchored displacement window is filled identically to a full-series run, but they produce no
    trades/frames. start/end None means from-first / to-last."""
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
               iso=a["iso"][sl], path=a["path"], n=hi_i - warm)
    rec_start = lo_i - warm
    return out, rec_start


@njit(cache=True)
def _core(cm, o, h, l, c, ep, win_len, thr, tp, sl, prev_block, prev_win, prev_thr,
          block_after_tp, min_r2, block_ny, block_ln, rec_start):
    n = c.shape[0]
    pos = np.zeros(n, np.int8)
    entry_px = np.full(n, np.nan)
    disp_arr = np.full(n, np.nan)
    prevmv_arr = np.full(n, np.nan)
    r2_arr = np.full(n, np.nan)
    cum = np.zeros(n)
    unreal = np.full(n, np.nan)
    entry_dir = np.zeros(n, np.int8)        # +1/-1 on the bar a trade opens, else 0
    exit_code = np.zeros(n, np.int8)         # 1 tp / 2 stop / 3 session / 4 open, else 0
    exit_px_arr = np.full(n, np.nan)
    # trades (upper bound n): dir, entry_i, exit_i, entry_px, exit_px, pts, exit_code
    t_dir = np.zeros(n, np.int8); t_ei = np.zeros(n, np.int64); t_xi = np.zeros(n, np.int64)
    t_ep = np.zeros(n); t_xp = np.zeros(n); t_pts = np.zeros(n); t_code = np.zeros(n, np.int8)
    m = 0

    p = 0; e_px = np.nan; e_i = -1; anchor = 0; cum_v = 0.0
    skip = False; r2_prev = np.nan; last_pts = np.nan; have_last = False

    for i in range(n):
        gap = i > 0 and (ep[i] - ep[i - 1]) / 60.0 > 60
        sess = (900 <= cm[i] < 960) or (block_ny and 510 <= cm[i] < 540) \
            or (block_ln and 120 <= cm[i] < 150) or gap
        closed = False; xcode = 0; xpx = np.nan

        if p > 0:
            if sess:
                xpx = c[i]; xcode = 3
            elif l[i] <= e_px - sl:
                xpx = e_px - sl; xcode = 2
            elif h[i] >= e_px + tp:
                xpx = e_px + tp; xcode = 1
        elif p < 0:
            if sess:
                xpx = c[i]; xcode = 3
            elif h[i] >= e_px + sl:
                xpx = e_px + sl; xcode = 2
            elif l[i] <= e_px - tp:
                xpx = e_px - tp; xcode = 1

        if xcode != 0:
            pts = (xpx - e_px) if p > 0 else (e_px - xpx)
            cum_v += pts * 2.0
            t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = i; t_ep[m] = e_px
            t_xp[m] = xpx; t_pts[m] = pts; t_code[m] = xcode; m += 1
            exit_code[i] = xcode; exit_px_arr[i] = xpx
            last_pts = pts; have_last = True
            p = 0; e_px = np.nan; e_i = -1; closed = True

        reset = (i == 0) or sess or closed
        if reset:
            anchor = i
        bs = i - anchor
        lookback = win_len if bs > win_len else bs
        disp = (c[i] - c[i - lookback]) if bs >= 1 else np.nan
        disp_arr[i] = disp

        # leg R2 over [anchor..i] (matches the pine ta.correlation(close,bar_index,legLen)^2)
        leg = bs + 1
        r2 = np.nan
        if leg >= 3:
            s = i - leg + 1
            mx = (leg - 1) / 2.0
            my = 0.0
            for k in range(leg):
                my += c[s + k]
            my /= leg
            sxy = 0.0; sxx = 0.0; syy = 0.0
            for k in range(leg):
                dx = k - mx; dy = c[s + k] - my
                sxy += dx * dy; sxx += dx * dx; syy += dy * dy
            if sxx > 0 and syy > 0:
                r2 = sxy * sxy / (sxx * syy)
        r2_arr[i] = r2

        if closed and block_after_tp and have_last and last_pts > 0 \
                and not np.isnan(r2_prev) and r2_prev >= min_r2:
            skip = True

        long_sig = (not np.isnan(disp)) and disp <= -thr
        short_sig = (not np.isnan(disp)) and disp >= thr
        prev_avail = i >= lookback + prev_win
        pm = (c[i - lookback] - c[i - lookback - prev_win]) if prev_avail else np.nan
        prevmv_arr[i] = pm
        long_ok = long_sig and ((not prev_block) or ((not np.isnan(pm)) and pm > prev_thr))
        short_ok = short_sig and ((not prev_block) or ((not np.isnan(pm)) and pm < -prev_thr))
        want = long_ok or short_ok
        # warm-up bars (i < rec_start) fill the window/anchor state but never open a trade, so the
        # recorded range starts genuinely flat with a fully-warmed displacement window.
        flat_ready = p == 0 and not sess and i >= rec_start
        blocked = skip
        if skip and want and flat_ready:
            skip = False

        if flat_ready and not blocked:
            if long_ok and not short_ok:
                p = 1; e_px = c[i]; e_i = i; entry_dir[i] = 1
            elif short_ok and not long_ok:
                p = -1; e_px = c[i]; e_i = i; entry_dir[i] = -1

        pos[i] = p
        entry_px[i] = e_px if p != 0 else np.nan
        cum[i] = cum_v
        if p != 0:
            unreal[i] = ((c[i] - e_px) if p > 0 else (e_px - c[i])) * 2.0
        r2_prev = r2

    # open trade at end
    open_i = -1
    if p != 0:
        pts = (c[n - 1] - e_px) if p > 0 else (e_px - c[n - 1])
        cum_v += pts * 2.0
        t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = n - 1; t_ep[m] = e_px
        t_xp[m] = c[n - 1]; t_pts[m] = pts; t_code[m] = 4; m += 1
        exit_code[n - 1] = 4; exit_px_arr[n - 1] = c[n - 1]
        cum[n - 1] = cum_v
        open_i = n - 1

    return (pos, entry_px, disp_arr, prevmv_arr, r2_arr, cum, unreal, entry_dir,
            exit_code, exit_px_arr,
            t_dir[:m], t_ei[:m], t_xi[:m], t_ep[:m], t_xp[:m], t_pts[:m], t_code[:m], open_i)


def _ct_iso(epoch_sec):
    from datetime import datetime
    return datetime.fromtimestamp(epoch_sec, port.CT).isoformat()


def build_run(dataset, cfg, start=None, end=None):
    """Run the numba core over a CT-date range [start,end] (ISO prefixes, inclusive) and adapt to
    (frames, trades, meta) for write_parquet. A lead-in of warm-up bars fills the displacement window
    so trades in the recorded range are identical to a full-series run over the same span. start/end
    None -> whole dataset. cfg keys: win_len, thr, tp, sl, prev_block, prev_win, prev_thr,
    block_after_tp, min_r2, block_ny, block_ln."""
    lead = max(cfg["win_len"] + cfg["prev_win"] + 2, 90)
    a, rec_start = slice_bars(dataset, start, end, lead=lead)
    cm, o, h, l, c, ep = a["cm"], a["o"], a["h"], a["l"], a["c"], a["ep"]
    (pos, entry_px, disp, prevmv, r2, cum, unreal, entry_dir, exit_code, exit_px,
     t_dir, t_ei, t_xi, t_ep, t_xp, t_pts, t_code, open_i) = _core(
        cm, o, h, l, c, ep, cfg["win_len"], cfg["thr"], cfg["tp"], cfg["sl"],
        cfg["prev_block"], cfg["prev_win"], cfg["prev_thr"], cfg["block_after_tp"],
        cfg["min_r2"], cfg["block_ny"], cfg["block_ln"], rec_start)
    n = c.shape[0]

    # Frames/trades are emitted only for the RECORDED range [rec_start, n); bar index is re-based to 0.
    def ri(i):
        return int(i) - rec_start

    trades = []
    cum_running = 0.0
    for k in range(len(t_dir)):
        d = int(t_dir[k]); ei = int(t_ei[k]); xi = int(t_xi[k])
        if ei < rec_start:      # (can't happen -- entries gated to rec_start -- but be safe)
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

    base_cum = float(cum[rec_start - 1]) if rec_start > 0 else 0.0   # re-baseline cum to 0 at rec_start
    frames = []
    for i in range(rec_start, n):
        ecode = int(exit_code[i])
        ev_exit = (_EXIT_CODE[ecode], float(exit_px[i])) if ecode != 0 else None
        ed = int(entry_dir[i])
        ev_entry = (ed, float(entry_px[i])) if ed != 0 else None
        frames.append(dict(
            i=ri(i), time=_ct_iso(ep[i]), o=float(o[i]), h=float(h[i]), l=float(l[i]), c=float(c[i]),
            res=None, supp=None, run=(None if np.isnan(disp[i]) else float(disp[i])), r2=None,
            long_sig=bool((not np.isnan(disp[i])) and disp[i] <= -cfg["thr"]),
            short_sig=bool((not np.isnan(disp[i])) and disp[i] >= cfg["thr"]),
            long_arm=False, short_arm=False,
            entry=ev_entry, exit=ev_exit, pos=int(pos[i]),
            entry_px=(None if pos[i] == 0 else float(entry_px[i])),
            stop_level=None, stop_kind=None, cum_usd=float(cum[i]) - base_cum,
            unreal_usd=(None if np.isnan(unreal[i]) else float(unreal[i]))))

    net = sum(t["pts"] for t in trades)
    wins = sum(1 for t in trades if t["pts"] > 0)
    nt = len(trades)
    gl = -sum(t["pts"] for t in trades if t["pts"] <= 0)
    gp = sum(t["pts"] for t in trades if t["pts"] > 0)
    st = dict(n=nt, net=net, usd=net * 2.0, wins=wins, losses=nt - wins,
              wr=100.0 * wins / nt if nt else 0.0, pf=(gp / gl) if gl > 0 else float("inf"),
              avg=net / nt if nt else 0.0)
    meta_cfg = dict(strategy="window_displacement_fade", **{k: cfg[k] for k in cfg}, mult=2.0)
    meta = dict(file=a["path"], tag=None, n_bars=len(frames), cfg=meta_cfg, stats=st, exact=False,
                start=start, end=end)
    return frames, trades, meta


def verify(dataset, cfg):
    """Assert the numba trade list equals the pure-Python port -- the oracle gate."""
    a = load_bars(dataset)
    bars = [(int(a["cm"][i]), float(a["o"][i]), float(a["h"][i]), float(a["l"][i]),
             float(a["c"][i]), float(a["ep"][i])) for i in range(a["n"])]
    ref = port.run(bars, win_len=cfg["win_len"], thr=cfg["thr"], tp=cfg["tp"], sl=cfg["sl"],
                   prev_block=cfg["prev_block"], prev_win=cfg["prev_win"], prev_thr=cfg["prev_thr"],
                   block_after_tp=cfg["block_after_tp"], min_r2=cfg["min_r2"],
                   block_ny=cfg["block_ny"], block_ln=cfg["block_ln"])
    _, trades, _ = build_run(dataset, cfg)
    got = [t["pts"] for t in trades]
    if len(ref) != len(got):
        return False, f"count mismatch: port={len(ref)} sim={len(got)}"
    for k, (rp, gp) in enumerate(zip(ref, got)):
        if abs(rp - gp) > 1e-6:
            return False, f"trade #{k} pts mismatch: port={rp} sim={gp}"
    return True, f"exact match on {len(ref)} trades"


DEFAULT_CFG = dict(win_len=port.WIN_LEN, thr=port.THR, tp=port.TP, sl=port.SL,
                   prev_block=port.PREV_BLOCK, prev_win=port.PREV_WIN, prev_thr=port.PREV_THR,
                   block_after_tp=port.BLOCK_AFTER_TP, min_r2=port.MIN_R2,
                   block_ny=port.BLOCK_NY, block_ln=port.BLOCK_LN)


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
