#!/usr/bin/env python3
"""Fast numba engine for "OD running-extreme break", for the UI's "New Run".

Mirrors backtest/od_runbreak_bt.py (the reference port) branch-for-branch. See that file for the
premise and for the honest result -- the pattern does NOT pay; this exists so the replay UI can show
the structure bar-by-bar (fall -> retest -> consolidation -> break) rather than to trade it.

Frame channels reused by the existing frontend:
  res    = the phase-2 running extreme (the level a break of which is the entry)
  supp   = the structural stop reference (running extreme of the fall)
  anchor = the 120 break level that started the whole sequence

Like the other engines this runs at slip=0 (the UI inspects fills, it does not quote P&L);
verify() therefore compares against port.run(slip=0.0).
"""
import os
import sys
import numpy as np
from numba import njit
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))
import od_runbreak_bt as port
import open_drive_bt as odport

_EXIT_CODE = {0: None, 1: "stop", 2: "tp", 3: "session"}

_BARS_CACHE = {}


def _ct_iso(epoch_sec):
    return datetime.fromtimestamp(epoch_sec, odport.CT).isoformat()


FWD_2026 = os.path.join(os.path.dirname(__file__), "..", "ohlcv", "mnq_fwd_2026.csv")


def load_bars(dataset):
    """dataset: 'oos' | 'fwd2026' (the 2026-05-19..08-19 forward block, past the 5yr file's
    2026-06-23 end) | anything else = the 5yr file."""
    if dataset in _BARS_CACHE:
        return _BARS_CACHE[dataset]
    if dataset == "oos":
        path = odport.OOS
    elif dataset == "fwd2026":
        # The forward block starts 2026-05-19, so on its own the first 3 days have NO trailing
        # daily ATR (nan) and the port/sim disagree on the missing-ATR branch. Prepend the 5yr
        # file and keep only the bars past its end: the ATR is then warm from bar one.
        path = os.path.abspath(FWD_2026)
        base = odport.load(odport.FIVE_YR)
        cutoff = max(b[5] for b in base)
        bars = base + [b for b in odport.load(path) if b[5] > cutoff]
        bars.sort(key=lambda b: b[5])
        return _pack(dataset, path, bars)
    else:
        path = odport.FIVE_YR
    return _pack(dataset, path, odport.load(path))


def _pack(dataset, path, bars):
    n = len(bars)
    cm = np.empty(n, np.int32); o = np.empty(n); h = np.empty(n)
    lo = np.empty(n); c = np.empty(n); ep = np.empty(n)
    for i, b in enumerate(bars):
        cm[i], o[i], h[i], lo[i], c[i], ep[i] = b[0], b[1], b[2], b[3], b[4], b[5]
    a = dict(path=path, n=n, cm=cm, o=o, h=h, l=lo, c=c, ep=ep, bars=bars)
    _BARS_CACHE[dataset] = a
    return a


def _atr_per_bar(bars, atr_days):
    """The port's dict/date ATR flattened to a per-bar array (numba can't build dicts of dates)."""
    atr = odport._daily_atr(bars, atr_days)
    out = np.full(len(bars), np.nan)
    for i, b in enumerate(bars):
        d = datetime.fromtimestamp(b[5], odport.CT).date()
        v = atr.get(d)
        if v is not None:
            out[i] = v
    return out


@njit(cache=True)
def _core(cm, o, h, l, c, ep, atr, trig_pts, rev_pts, thr, sl_ext, sl_mult, tp_pts, trail_pts,
          max_trades, rth_open_min, eod_min, attempt_mode, buf):
    n = cm.shape[0]
    t_dir = np.zeros(n, np.int8); t_ei = np.zeros(n, np.int64); t_xi = np.zeros(n, np.int64)
    t_ep = np.zeros(n); t_xp = np.zeros(n); t_pts = np.zeros(n); t_code = np.zeros(n, np.int8)
    nt = 0

    pos_a = np.zeros(n, np.int8)
    entry_dir = np.zeros(n, np.int8); entry_px_a = np.full(n, np.nan)
    exit_code = np.zeros(n, np.int8); exit_px_a = np.full(n, np.nan)
    res_a = np.full(n, np.nan); supp_a = np.full(n, np.nan); anchor_a = np.full(n, np.nan)
    pbreak = np.zeros(n, np.int8)     # bar the PAPER od-120 would have fired (+1 up, -1 down)
    prev_a = np.full(n, np.nan)       # its fill level
    revbar = np.zeros(n, np.int8)     # bar the 120pt reversal completed (fall declared over later)
    revpx_a = np.full(n, np.nan)
    stop_a = np.full(n, np.nan); epx_a = np.full(n, np.nan)
    cum = np.zeros(n); unreal = np.full(n, np.nan)

    rth = np.nan; took = False
    pend_dir = 0; pend_lvl = np.nan
    anchor_cur = np.nan
    active = False; bd = 0; phase = 0
    ext = np.nan; runx = np.nan; lowref = np.nan; armed = False
    att_hi = np.nan; att_since = np.nan; level = np.nan
    pos = 0; epx = np.nan; stop = np.nan; ei = -1; seq = 0
    run_cum = 0.0
    prev_ms = -10000

    for i in range(n):
        ms = cm[i] - rth_open_min
        gap = (i > 0) and ((ep[i] - ep[i - 1]) / 60.0 > 60)
        eod = (cm[i] >= eod_min) and (cm[i] < 960)
        new_day = (ms == 0) or (prev_ms < 0 and ms >= 0) or gap

        if new_day:
            rth = np.nan; took = False; pend_dir = 0
            active = False; phase = 0; seq = 0
            anchor_cur = np.nan
            att_hi = np.nan; att_since = np.nan; level = np.nan

        if ms >= 0 and ms < 60 and np.isnan(rth):
            rth = o[i]

        if pos != 0 and (eod or gap):
            pts = (c[i] - epx) if pos > 0 else (epx - c[i])
            t_dir[nt] = pos; t_ei[nt] = ei; t_xi[nt] = i; t_ep[nt] = epx
            t_xp[nt] = c[i]; t_pts[nt] = pts; t_code[nt] = 3; nt += 1
            run_cum += pts; exit_code[i] = 3; exit_px_a[i] = c[i]; pos = 0

        if active and not eod:
            if pos != 0 and ei != i:
                done = False
                if pos > 0:
                    if l[i] <= stop:
                        pts = stop - epx; xp = stop; code = 1; done = True
                    elif tp_pts > 0 and h[i] >= epx + tp_pts:
                        pts = tp_pts; xp = epx + tp_pts; code = 2; done = True
                    elif trail_pts > 0:
                        if h[i] - trail_pts > stop:
                            stop = h[i] - trail_pts
                else:
                    if h[i] >= stop:
                        pts = epx - stop; xp = stop; code = 1; done = True
                    elif tp_pts > 0 and l[i] <= epx - tp_pts:
                        pts = tp_pts; xp = epx - tp_pts; code = 2; done = True
                    elif trail_pts > 0:
                        if l[i] + trail_pts < stop:
                            stop = l[i] + trail_pts
                if done:
                    t_dir[nt] = pos; t_ei[nt] = ei; t_xi[nt] = i; t_ep[nt] = epx
                    t_xp[nt] = xp; t_pts[nt] = pts; t_code[nt] = code; nt += 1
                    run_cum += pts; exit_code[i] = code; exit_px_a[i] = xp; pos = 0
                    phase = 2; armed = False
                    if bd > 0:
                        runx = h[i]; lowref = l[i]
                    else:
                        runx = l[i]; lowref = h[i]
                    att_hi = np.nan; att_since = np.nan; level = np.nan

            if pos == 0:
                if attempt_mode:
                    if bd > 0:
                        if np.isnan(ext) or l[i] < ext:
                            ext = l[i]
                            att_hi = np.nan; att_since = np.nan
                        if np.isnan(att_hi) or h[i] > att_hi:
                            att_hi = h[i]; att_since = l[i]
                        else:
                            if l[i] < att_since:
                                att_since = l[i]
                            if att_hi - att_since >= thr:
                                level = att_hi; armed = False
                        if not np.isnan(level):
                            if (not armed) and h[i] >= level:
                                armed = True
                            if armed and h[i] >= level + buf and seq < max_trades:
                                lvl = level + buf
                                epx = o[i] if o[i] > lvl else lvl
                                pos = 1; seq += 1; ei = i
                                if sl_ext:
                                    stop = ext
                                else:
                                    stop = epx - sl_mult * atr[i] if not np.isnan(atr[i]) else epx - 25.0
                                if epx - stop < 5.0:
                                    stop = epx - 5.0
                                entry_dir[i] = 1; entry_px_a[i] = epx
                                level = np.nan; armed = False; att_hi = np.nan
                    else:
                        if np.isnan(ext) or h[i] > ext:
                            ext = h[i]
                            att_hi = np.nan; att_since = np.nan
                        if np.isnan(att_hi) or l[i] < att_hi:
                            att_hi = l[i]; att_since = h[i]
                        else:
                            if h[i] > att_since:
                                att_since = h[i]
                            if att_since - att_hi >= thr:
                                level = att_hi; armed = False
                        if not np.isnan(level):
                            if (not armed) and l[i] <= level:
                                armed = True
                            if armed and l[i] <= level - buf and seq < max_trades:
                                lvl = level - buf
                                epx = o[i] if o[i] < lvl else lvl
                                pos = -1; seq += 1; ei = i
                                if sl_ext:
                                    stop = ext
                                else:
                                    stop = epx + sl_mult * atr[i] if not np.isnan(atr[i]) else epx + 25.0
                                if stop - epx < 5.0:
                                    stop = epx + 5.0
                                entry_dir[i] = -1; entry_px_a[i] = epx
                                level = np.nan; armed = False; att_hi = np.nan
                elif phase == 1:
                    if bd > 0:
                        if np.isnan(ext) or l[i] < ext:
                            ext = l[i]
                        if h[i] - ext >= thr:
                            phase = 2; runx = h[i]; lowref = ext; armed = True
                    else:
                        if np.isnan(ext) or h[i] > ext:
                            ext = h[i]
                        if ext - l[i] >= thr:
                            phase = 2; runx = l[i]; lowref = ext; armed = True
                elif phase == 2:
                    if bd > 0:
                        if l[i] < lowref:
                            lowref = l[i]
                        if (not armed) and (runx - l[i] >= thr):
                            armed = True
                        if armed and h[i] > runx and seq < max_trades:
                            epx = o[i] if o[i] > runx else runx
                            pos = 1; seq += 1; armed = False; ei = i
                            if sl_ext:
                                stop = lowref
                            else:
                                stop = epx - sl_mult * atr[i] if not np.isnan(atr[i]) else epx - 25.0
                            if epx - stop < 5.0:
                                stop = epx - 5.0
                            entry_dir[i] = 1; entry_px_a[i] = epx
                        if h[i] > runx:
                            runx = h[i]
                    else:
                        if h[i] > lowref:
                            lowref = h[i]
                        if (not armed) and (h[i] - runx >= thr):
                            armed = True
                        if armed and l[i] < runx and seq < max_trades:
                            epx = o[i] if o[i] < runx else runx
                            pos = -1; seq += 1; armed = False; ei = i
                            if sl_ext:
                                stop = lowref
                            else:
                                stop = epx + sl_mult * atr[i] if not np.isnan(atr[i]) else epx + 25.0
                            if stop - epx < 5.0:
                                stop = epx + 5.0
                            entry_dir[i] = -1; entry_px_a[i] = epx
                        if l[i] < runx:
                            runx = l[i]

        if pend_dir != 0 and (not active) and (not eod):
            lvl = pend_lvl - rev_pts * pend_dir
            hit = (l[i] <= lvl) if pend_dir > 0 else (h[i] >= lvl)
            if hit:
                active = True; bd = pend_dir; phase = 1; ext = np.nan; pend_dir = 0
                att_hi = np.nan; att_since = np.nan; level = np.nan
                revbar[i] = bd; revpx_a[i] = lvl

        in_win = (ms >= 0) and (ms < 330) and (not eod)
        if pend_dir == 0 and (not active) and in_win and (not took) and (not np.isnan(rth)):
            up_lvl = rth + trig_pts; dn_lvl = rth - trig_pts
            up = h[i] >= up_lvl; dn = l[i] <= dn_lvl
            if up or dn:
                took = True
                if up:
                    pend_dir = 1
                    pend_lvl = o[i] if o[i] > up_lvl else up_lvl
                else:
                    pend_dir = -1
                    pend_lvl = o[i] if o[i] < dn_lvl else dn_lvl
                anchor_cur = pend_lvl
                pbreak[i] = pend_dir; prev_a[i] = pend_lvl

        if active and attempt_mode:
            if not np.isnan(level):
                res_a[i] = level
            if not np.isnan(ext):
                supp_a[i] = ext
        elif active and phase == 2:
            res_a[i] = runx; supp_a[i] = lowref
        anchor_a[i] = anchor_cur
        pos_a[i] = pos
        if pos != 0:
            stop_a[i] = stop; epx_a[i] = epx
            unreal[i] = ((c[i] - epx) if pos > 0 else (epx - c[i])) * 2.0
        cum[i] = run_cum * 2.0
        prev_ms = ms

    return (t_dir[:nt], t_ei[:nt], t_xi[:nt], t_ep[:nt], t_xp[:nt], t_pts[:nt], t_code[:nt],
            pos_a, entry_dir, entry_px_a, exit_code, exit_px_a, res_a, supp_a, anchor_a,
            stop_a, epx_a, cum, unreal, pbreak, prev_a, revbar, revpx_a)


def _run_core(dataset, cfg):
    a = load_bars(dataset)
    atr = _atr_per_bar(a["bars"], int(cfg["atr_days"]))
    return a, atr, _core(
        a["cm"], a["o"], a["h"], a["l"], a["c"], a["ep"], atr,
        float(cfg["trig_pts"]), float(cfg["rev_pts"]), float(cfg["thr"]),
        cfg["sl_mode_ext"], float(cfg["sl_mult"]), float(cfg["tp_pts"]), float(cfg["trail_pts"]),
        int(cfg["max_trades"]), odport.RTH_OPEN_MIN, odport.EOD_MIN,
        bool(cfg.get("attempt_mode", True)), float(cfg.get("buf", 15.0)))


def build_run(dataset, cfg, start=None, end=None):
    a, atr, out = _run_core(dataset, cfg)
    (t_dir, t_ei, t_xi, t_ep, t_xp, t_pts, t_code, pos, entry_dir, entry_px, exit_code, exit_px,
     res, supp, anchor, stop_lvl, epx_a, cum, unreal, pbreak, prevpx, revbar, revpx) = out
    n = a["n"]; ep = a["ep"]; o = a["o"]; h = a["h"]; l = a["l"]; c = a["c"]

    rec_start = 0
    if start or end:
        for i in range(n):
            d = datetime.fromtimestamp(ep[i], odport.CT).date().isoformat()
            if start and d < start:
                continue
            rec_start = i
            break
    rec_end = n
    if end:
        for i in range(rec_start, n):
            d = datetime.fromtimestamp(ep[i], odport.CT).date().isoformat()
            if d > end:
                rec_end = i
                break

    def ri(i):
        return int(i) - rec_start

    trades = []
    cum_running = 0.0
    for k in range(len(t_dir)):
        ei = int(t_ei[k]); xi = int(t_xi[k])
        if ei < rec_start or ei >= rec_end:
            continue
        d = int(t_dir[k]); epx = float(t_ep[k]); xpx = float(t_xp[k]); pts = float(t_pts[k])
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
    for i in range(rec_start, rec_end):
        ecode = int(exit_code[i])
        ev_exit = (_EXIT_CODE[ecode], float(exit_px[i])) if ecode != 0 else None
        ed = int(entry_dir[i])
        ev_entry = (ed, float(entry_px[i])) if ed != 0 else None
        frames.append(dict(
            i=ri(i), time=_ct_iso(ep[i]), o=float(o[i]), h=float(h[i]), l=float(l[i]), c=float(c[i]),
            res=(None if np.isnan(res[i]) else float(res[i])),
            supp=(None if np.isnan(supp[i]) else float(supp[i])),
            run=None, r2=None,
            long_sig=bool(revbar[i] < 0), short_sig=bool(revbar[i] > 0),
            long_arm=bool(pbreak[i] > 0), short_arm=bool(pbreak[i] < 0),
            paper_break=(None if pbreak[i] == 0 else int(pbreak[i])),
            paper_break_px=(None if np.isnan(prevpx[i]) else float(prevpx[i])),
            reversal=(None if revbar[i] == 0 else int(revbar[i])),
            reversal_px=(None if np.isnan(revpx[i]) else float(revpx[i])),
            entry=ev_entry, exit=ev_exit, pos=int(pos[i]),
            entry_px=(None if pos[i] == 0 else float(epx_a[i])),
            stop_level=(None if np.isnan(stop_lvl[i]) else float(stop_lvl[i])),
            stop_kind=("struct" if not np.isnan(stop_lvl[i]) else None),
            anchor=(None if np.isnan(anchor[i]) else float(anchor[i])),
            cum_usd=float(cum[i]) - base_cum,
            unreal_usd=(None if np.isnan(unreal[i]) else float(unreal[i]))))

    net = sum(t["pts"] for t in trades)
    wins = sum(1 for t in trades if t["pts"] > 0)
    nt = len(trades)
    gl = -sum(t["pts"] for t in trades if t["pts"] <= 0)
    gp = sum(t["pts"] for t in trades if t["pts"] > 0)
    st = dict(n=nt, net=net, usd=net * 2.0, wins=wins, losses=nt - wins,
              wr=100.0 * wins / nt if nt else 0.0, pf=(gp / gl) if gl > 0 else None,
              avg=net / nt if nt else 0.0)
    meta_cfg = dict(strategy="od_runbreak", **{k: cfg[k] for k in cfg}, mult=2.0)
    meta = dict(file=a["path"], tag=None, n_bars=len(frames), cfg=meta_cfg, stats=st, exact=False,
                start=start, end=end)
    return frames, trades, meta


def verify(dataset, cfg):
    """Assert the numba trade list equals the pure-Python port -- the oracle gate."""
    a = load_bars(dataset)
    ref = port.run(a["bars"], trig_pts=cfg["trig_pts"], rev_pts=cfg["rev_pts"], thr=cfg["thr"],
                   sl_mode=("ext" if cfg["sl_mode_ext"] else "atr"), sl_mult=cfg["sl_mult"],
                   atr_days=int(cfg["atr_days"]), tp_pts=cfg["tp_pts"],
                   trail_pts=cfg["trail_pts"], max_trades=int(cfg["max_trades"]), slip=0.0,
                   attempt_mode=cfg.get("attempt_mode", True), buf=cfg.get("buf", 15.0))
    _, trades, _ = build_run(dataset, cfg)
    got = [t["pts"] for t in trades]
    if len(ref) != len(got):
        return False, f"count mismatch: port={len(ref)} sim={len(got)}"
    for k, (rp, gp) in enumerate(zip([r[3] for r in ref], got)):
        if abs(rp - gp) > 1e-6:
            return False, f"trade #{k} pts mismatch: port={rp} sim={gp}"
    return True, f"exact match on {len(ref)} trades"


if __name__ == "__main__":
    cfg = dict(trig_pts=120.0, rev_pts=120.0, thr=40.0, sl_mode_ext=True, sl_mult=1.0,
               atr_days=3, tp_pts=150.0, trail_pts=0.0, max_trades=99,
               attempt_mode=True, buf=15.0)
    ok, msg = verify("mnq_5yr", cfg)
    print("verify:", ok, msg)
