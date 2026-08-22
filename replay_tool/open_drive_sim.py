#!/usr/bin/env python3
"""Fast numba simulation engine for open_drive ("Otaru"), for the UI's "New Run".

Mirrors backtest/open_drive_bt.py (the reference port) branch-for-branch:
  ANCHOR  : open of the first RTH bar (08:30 CT), frozen for the day. 60-min grace window so a
            missing 08:30 bar degrades to a late anchor rather than skipping the day.
  TRIGGER : resting STOP orders at anchor +/- trig_pts, armed from settle_min past the open until
            entry_end_min. Whichever side price reaches first fills; the other is cancelled.
  FILL    : the LEVEL when the bar trades through it, the bar OPEN when the bar gapped past it.
            This is the whole ballgame -- always-fill-at-level inflates net ~2x.
  EXIT    : ATR stop (sl_mult * trailing daily ATR, frozen at entry) or EOD flatten at 15:00 CT.
            No take-profit by design.
  FILTER  : optional |pre-open slope| gate over the 60 min ending at the open.

The daily ATR is dict/date-based (numba can't build it), so it is precomputed ONCE in Python as a
per-bar array and passed into the JIT core -- the "precompute then JIT, no per-bar Python" rule from
backtest/PERF_NOTES.md. verify() asserts the numba trade list equals open_drive_bt.run().

NOTE ON SLIPPAGE: the port charges slip once per round-trip; this engine runs at slip=0 so the UI
shows raw fills (the replay UI is for INSPECTING trades, not for quoting P&L). verify() therefore
compares against port.run(slip=0.0).
"""
import os
import sys
import numpy as np
from numba import njit
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))
import open_drive_bt as port  # the reference oracle

# 0 = no exit this bar. Codes mirror the port's reason strings.
_EXIT_CODE = {0: None, 1: "atrstop", 2: "session", 3: "open"}

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
    dates = np.array([datetime.fromtimestamp(e, port.CT).date().toordinal() for e in ep], np.int64)
    arr = dict(cm=cm, o=o, h=h, l=lo, c=c, ep=ep, iso=iso, dates=dates, path=path, n=n)
    _BARS_CACHE[dataset] = arr
    return arr


def _atr_per_bar(dates, h, l, ndays):
    """Trailing avg of prior-day full ranges as a per-bar array. Matches open_drive_bt._daily_atr."""
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
    return out, lo_i - warm


@njit(cache=True)
def _core(cm, o, h, l, c, ep, atr_bar, trig_pts, settle_min, entry_end_min,
          use_slope_gate, slope_min, use_atr_stop, sl_mult,
          enable_long, enable_short, rec_start):
    n = c.shape[0]
    RTH = 510; EOD = 900; PRE_LEN = 60; PRE_MIN_BARS = 55
    pos = np.zeros(n, np.int8)
    entry_px_a = np.full(n, np.nan)
    up_arr = np.full(n, np.nan); dn_arr = np.full(n, np.nan)
    anchor_arr = np.full(n, np.nan)
    stop_arr = np.full(n, np.nan)
    cum = np.zeros(n)
    unreal = np.full(n, np.nan)
    entry_dir = np.zeros(n, np.int8)
    exit_code = np.zeros(n, np.int8)
    exit_px_arr = np.full(n, np.nan)
    t_dir = np.zeros(n, np.int8); t_ei = np.zeros(n, np.int64); t_xi = np.zeros(n, np.int64)
    t_ep = np.zeros(n); t_xp = np.zeros(n); t_pts = np.zeros(n); t_code = np.zeros(n, np.int8)
    m = 0

    anchor = np.nan
    took = False
    pre_first = np.nan; pre_slope = np.nan; pre_bars = 0; pre_ready = False
    p = 0; e_px = np.nan; e_i = -1; stop_lvl = np.nan
    cum_v = 0.0
    prev_ms = -9999

    for i in range(n):
        ms = cm[i] - RTH
        gap = (i > 0) and (ep[i] - ep[i - 1]) / 60.0 > 60
        eod = (cm[i] >= EOD) and (cm[i] < 960)
        new_day = (ms == 0) or (prev_ms < 0 and ms >= 0) or gap

        if new_day:
            anchor = np.nan
            took = False
            pre_first = np.nan
            pre_bars = 0

        # pre-open slope over the 60 min ending at the open
        if ms >= -PRE_LEN and ms < 0:
            if np.isnan(pre_first):
                pre_first = c[i]
                pre_bars = 0
            pre_bars += 1
            pre_slope = (c[i] - pre_first) / 60.0
            pre_ready = pre_bars >= PRE_MIN_BARS

        # anchor: first bar at/after the open, 60-min grace
        if ms >= 0 and ms < 60 and np.isnan(anchor):
            anchor = o[i]

        # ---- ATR stop: resting protective order, from the bar AFTER entry ----
        if p != 0 and (not np.isnan(stop_lvl)) and i != e_i:
            hit = False; xpx = np.nan
            if p > 0 and l[i] <= stop_lvl:
                xpx = stop_lvl; hit = True
            elif p < 0 and h[i] >= stop_lvl:
                xpx = stop_lvl; hit = True
            if hit:
                pts = (xpx - e_px) if p > 0 else (e_px - xpx)
                cum_v += pts * 2.0
                t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = i; t_ep[m] = e_px
                t_xp[m] = xpx; t_pts[m] = pts; t_code[m] = 1; m += 1
                exit_code[i] = 1; exit_px_arr[i] = xpx
                p = 0; e_px = np.nan; e_i = -1; stop_lvl = np.nan

        # ---- EOD / gap flatten ----
        if p != 0 and (eod or gap):
            xpx = c[i]
            pts = (xpx - e_px) if p > 0 else (e_px - xpx)
            cum_v += pts * 2.0
            t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = i; t_ep[m] = e_px
            t_xp[m] = xpx; t_pts[m] = pts; t_code[m] = 2; m += 1
            exit_code[i] = 2; exit_px_arr[i] = xpx
            p = 0; e_px = np.nan; e_i = -1; stop_lvl = np.nan

        # ---- entry: resting stop, level fill or bar-open on a gap-through ----
        in_win = (ms >= settle_min) and (ms < entry_end_min) and (not eod)
        slope_ok = (not use_slope_gate) or (pre_ready and (not np.isnan(pre_slope))
                                            and abs(pre_slope) >= slope_min)
        if p == 0 and in_win and (not took) and slope_ok and (not np.isnan(anchor)) and i >= rec_start:
            up_lvl = anchor + trig_pts
            dn_lvl = anchor - trig_pts
            a_atr = atr_bar[i]
            if h[i] >= up_lvl and enable_long:
                px = o[i] if o[i] > up_lvl else up_lvl
                p = 1; e_px = px; e_i = i; took = True; entry_dir[i] = 1
                stop_lvl = (px - sl_mult * a_atr) if (use_atr_stop and not np.isnan(a_atr)) else np.nan
            elif l[i] <= dn_lvl and enable_short:
                px = o[i] if o[i] < dn_lvl else dn_lvl
                p = -1; e_px = px; e_i = i; took = True; entry_dir[i] = -1
                stop_lvl = (px + sl_mult * a_atr) if (use_atr_stop and not np.isnan(a_atr)) else np.nan

        if not np.isnan(anchor):
            anchor_arr[i] = anchor
            up_arr[i] = anchor + trig_pts
            dn_arr[i] = anchor - trig_pts
        pos[i] = p
        entry_px_a[i] = e_px if p != 0 else np.nan
        stop_arr[i] = stop_lvl if p != 0 else np.nan
        cum[i] = cum_v
        if p != 0:
            unreal[i] = ((c[i] - e_px) if p > 0 else (e_px - c[i])) * 2.0
        prev_ms = ms

    open_i = -1
    if p != 0:
        pts = (c[n - 1] - e_px) if p > 0 else (e_px - c[n - 1])
        cum_v += pts * 2.0
        t_dir[m] = p; t_ei[m] = e_i; t_xi[m] = n - 1; t_ep[m] = e_px
        t_xp[m] = c[n - 1]; t_pts[m] = pts; t_code[m] = 3; m += 1
        exit_code[n - 1] = 3; exit_px_arr[n - 1] = c[n - 1]
        cum[n - 1] = cum_v
        open_i = n - 1

    return (pos, entry_px_a, up_arr, dn_arr, anchor_arr, stop_arr, cum, unreal, entry_dir,
            exit_code, exit_px_arr,
            t_dir[:m], t_ei[:m], t_xi[:m], t_ep[:m], t_xp[:m], t_pts[:m], t_code[:m], open_i)


def build_run(dataset, cfg, start=None, end=None):
    # lead must cover the pre-open slope window and the ATR warm-up day boundary
    lead = max(int(cfg["entry_end_min"]) + 5, 150)
    a, rec_start = slice_bars(dataset, start, end, lead=lead)
    cm, o, h, l, c, ep = a["cm"], a["o"], a["h"], a["l"], a["c"], a["ep"]
    atr_bar = _atr_per_bar(a["dates"], h, l, int(cfg["atr_days"])) if cfg["use_atr_stop"] \
        else np.full(len(c), np.nan)
    (pos, entry_px, up_lvl, dn_lvl, anchor, stop_lvl, cum, unreal, entry_dir,
     exit_code, exit_px, t_dir, t_ei, t_xi, t_ep, t_xp, t_pts, t_code, open_i) = _core(
        cm, o, h, l, c, ep, atr_bar, cfg["trig_pts"], int(cfg["settle_min"]),
        int(cfg["entry_end_min"]), cfg["use_slope_gate"], cfg["slope_min"],
        cfg["use_atr_stop"], cfg["sl_mult"], cfg["enable_long"], cfg["enable_short"], rec_start)
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
        trades.append(dict(dir=d, entry_i=ri(ei), entry_time=_ct_iso(ep[ei]), entry_px=epx,
                           exit_i=ri(xi), exit_time=_ct_iso(ep[xi]), exit_px=xpx, pts=pts, usd=usd,
                           reason=_EXIT_CODE.get(int(t_code[k]), "?"), bars_held=xi - ei,
                           cum_usd=cum_running, mfe=mfe, mae=mae,
                           mfe_usd=mfe * 2.0, mae_usd=mae * 2.0))

    base_cum = float(cum[rec_start - 1]) if rec_start > 0 else 0.0
    frames = []
    for i in range(rec_start, n):
        ecode = int(exit_code[i])
        ev_exit = (_EXIT_CODE[ecode], float(exit_px[i])) if ecode != 0 else None
        ed = int(entry_dir[i])
        ev_entry = (ed, float(entry_px[i])) if ed != 0 else None
        # res/supp are the generic "two horizontal levels" channel the frontend already draws --
        # here they carry the two drive-trigger rails.
        frames.append(dict(
            i=ri(i), time=_ct_iso(ep[i]), o=float(o[i]), h=float(h[i]), l=float(l[i]), c=float(c[i]),
            res=(None if np.isnan(up_lvl[i]) else float(up_lvl[i])),
            supp=(None if np.isnan(dn_lvl[i]) else float(dn_lvl[i])),
            run=None, r2=None, long_sig=False, short_sig=False, long_arm=False, short_arm=False,
            entry=ev_entry, exit=ev_exit, pos=int(pos[i]),
            entry_px=(None if pos[i] == 0 else float(entry_px[i])),
            stop_level=(None if np.isnan(stop_lvl[i]) else float(stop_lvl[i])),
            stop_kind=("atr" if not np.isnan(stop_lvl[i]) else None),
            anchor=(None if np.isnan(anchor[i]) else float(anchor[i])),
            cum_usd=float(cum[i]) - base_cum,
            unreal_usd=(None if np.isnan(unreal[i]) else float(unreal[i]))))

    net = sum(t["pts"] for t in trades)
    wins = sum(1 for t in trades if t["pts"] > 0)
    nt = len(trades)
    gl = -sum(t["pts"] for t in trades if t["pts"] <= 0)
    gp = sum(t["pts"] for t in trades if t["pts"] > 0)
    st = dict(n=nt, net=net, usd=net * 2.0, wins=wins, losses=nt - wins,
              wr=100.0 * wins / nt if nt else 0.0, pf=(gp / gl) if gl > 0 else float("inf"),
              avg=net / nt if nt else 0.0)
    meta_cfg = dict(strategy="open_drive", **{k: cfg[k] for k in cfg}, mult=2.0)
    meta = dict(file=a["path"], tag=None, n_bars=len(frames), cfg=meta_cfg, stats=st, exact=False,
                start=start, end=end)
    return frames, trades, meta


def verify(dataset, cfg):
    """Assert the numba trade list equals the pure-Python port -- the oracle gate.

    Compared at slip=0.0: this engine models fills only, the port charges slippage separately.
    """
    a = load_bars(dataset)
    bars = [(int(a["cm"][i]), float(a["o"][i]), float(a["h"][i]), float(a["l"][i]),
             float(a["c"][i]), float(a["ep"][i])) for i in range(a["n"])]
    ref = port.run(bars, trig_pts=cfg["trig_pts"], settle_min=int(cfg["settle_min"]),
                   entry_end_min=int(cfg["entry_end_min"]),
                   use_slope_gate=cfg["use_slope_gate"], slope_min=cfg["slope_min"],
                   enable_long=cfg["enable_long"], enable_short=cfg["enable_short"],
                   slip=0.0, fillmode="stop", use_atr_stop=cfg["use_atr_stop"],
                   sl_mult=cfg["sl_mult"], atr_days=int(cfg["atr_days"]))
    _, trades, _ = build_run(dataset, cfg)
    got = [t["pts"] for t in trades]
    if len(ref) != len(got):
        return False, f"count mismatch: port={len(ref)} sim={len(got)}"
    for k, (rp, gp) in enumerate(zip([r[3] for r in ref], got)):
        if abs(rp - gp) > 1e-6:
            return False, f"trade #{k} pts mismatch: port={rp} sim={gp}"
    return True, f"exact match on {len(ref)} trades"


DEFAULT_CFG = dict(trig_pts=120.0, settle_min=0, entry_end_min=330,
                   use_slope_gate=False, slope_min=0.75,
                   use_atr_stop=True, sl_mult=1.0, atr_days=14,
                   enable_long=True, enable_short=True)


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
        print(f"{a.dataset}: trades={meta['stats']['n']} net={meta['stats']['net']:.0f}pt "
              f"PF={meta['stats']['pf']:.2f}  ({time.time()-t0:.1f}s)")
