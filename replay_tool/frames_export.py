#!/usr/bin/env python3
"""
frames_export.py -- Milestone 1 of the replay-backtest UI (no UI yet).

Runs the VALIDATED port (backtest/slope_touch_fade_bt.py) over a CSV and records, per bar,
the full internal state the port normally discards, so a later UI can replay it. Also emits an
enriched trade list (with timestamps + exit reasons). Writes a JSON blob (+ optional parquet).

The recording trade-loop below is a line-for-line mirror of slope_touch_fade_bt.trade_loop:
same branch order, same conditions, same fill prices. The ONLY additions are (a) per-bar frame
records and (b) trade metadata (entry/exit bar index, time, reason). Behaviour is unchanged --
verify_matches() re-runs the real trade_loop and asserts the extracted trades are byte-identical.

USAGE
  python3 frames_export.py --oos                 # run the OOS csv (fast, good for iterating)
  python3 frames_export.py --file <csv>          # run any csv
  python3 frames_export.py                        # run the full 5yr file (slow: ~1.77M bars)
  # config flags mirror the port:
  python3 frames_export.py --oos --trail 80 --stop-buf 10   # enable trail+init stops
"""
import sys
import os
import json
import argparse

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _HAVE_ARROW = True
except ImportError:
    _HAVE_ARROW = False

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))
import slope_touch_fade_bt as port  # the validated engine -- do NOT reimplement detect/pivots/ols


def _ct_iso(epoch_sec):
    """Chicago-time ISO string for a frame timestamp (matches the port's CT normalization)."""
    from datetime import datetime
    return datetime.fromtimestamp(epoch_sec, port.CT).isoformat()


def _zoneinfo_london():
    from zoneinfo import ZoneInfo
    return ZoneInfo("Europe/London")


def build_frames(bars, sig, block_ny, block_ln, mult,
                 enable_trail, trail, enable_init, stop_buf, arms=None, keep_hours=None):
    """Mirror of port.trade_loop, but records per-bar frames + enriched trades.

    Returns (frames, trades):
      frames[i] = dict of everything the UI needs to draw bar i.
      trades[k] = dict with dir, entry/exit bar+time+px, pts, usd, reason, bars_held, cum_usd.
    The bare (dir,entry,exit,pts,usd) tuples embedded in each trade MUST equal port.trade_loop's
    output -- that's the verification invariant.

    arms=(long_arm, short_arm): per-bar bools for the red/green ARM dots (trend-into-S/R detected,
    before the pullback triangle). Recorded onto each frame; does NOT affect trades.

    keep_hours: optional set of LONDON hours (0-23). If given, ENTRIES are only allowed on bars whose
    London hour is in the set (a session-window "keep" filter); trades already open still exit
    normally. NOTE: this diverges from port.trade_loop, so verify is skipped when it's active.
    """
    long_sig, short_sig, fext_long, fext_short = sig
    long_arm, short_arm = arms if arms is not None else ([False] * len(bars), [False] * len(bars))
    ctmin = [b[0] for b in bars]
    # per-bar London hour (from epoch), only needed when keep_hours is set
    if keep_hours:
        from datetime import datetime, timezone
        _LDN = _zoneinfo_london()
        ldn_hour = [datetime.fromtimestamp(b[5], timezone.utc).astimezone(_LDN).hour for b in bars]
    else:
        ldn_hour = None
    high = [b[2] for b in bars]
    low = [b[3] for b in bars]
    close = [b[4] for b in bars]
    epoch = [b[5] for b in bars]
    res_line = [b[6] for b in bars]
    supp_line = [b[7] for b in bars]
    pine_run = [b[8] for b in bars]
    pine_r2 = [b[9] for b in bars]
    n = len(bars)

    pos = 0
    entry_px = init_stop = best = None
    entry_i = None
    cum_usd = 0.0
    # MFE/MAE tracking: the most-favorable and most-adverse PRICE seen since entry (intrabar,
    # via high/low). Reset on each entry; folded forward every open bar. Converted to points
    # relative to entry (sign-adjusted by direction) at close time.
    mfe_px = mae_px = None

    trades = []
    frames = [None] * n

    def _excursion_extend(i):
        """Fold bar i's high/low into the running favorable/adverse extremes (only while open)."""
        nonlocal mfe_px, mae_px
        if pos == 0:
            return
        hi, lo = high[i], low[i]
        if pos > 0:                       # long: favorable = higher, adverse = lower
            mfe_px = hi if mfe_px is None else max(mfe_px, hi)
            mae_px = lo if mae_px is None else min(mae_px, lo)
        else:                             # short: favorable = lower, adverse = higher
            mfe_px = lo if mfe_px is None else min(mfe_px, lo)
            mae_px = hi if mae_px is None else max(mae_px, hi)

    # per-bar exit annotation, filled as trades close
    def record_trade(direction, exit_px, exit_i, reason):
        nonlocal cum_usd
        pts = (exit_px - entry_px) if direction > 0 else (entry_px - exit_px)
        usd = pts * mult
        cum_usd += usd
        # MFE = favorable excursion in points (>=0); MAE = adverse excursion in points (<=0).
        if direction > 0:
            mfe = (mfe_px - entry_px) if mfe_px is not None else 0.0
            mae = (mae_px - entry_px) if mae_px is not None else 0.0
        else:
            mfe = (entry_px - mfe_px) if mfe_px is not None else 0.0
            mae = (entry_px - mae_px) if mae_px is not None else 0.0
        trades.append(dict(
            dir=direction,
            entry_i=entry_i, entry_time=_ct_iso(epoch[entry_i]), entry_px=entry_px,
            exit_i=exit_i, exit_time=_ct_iso(epoch[exit_i]), exit_px=exit_px,
            pts=pts, usd=usd, reason=reason,
            bars_held=exit_i - entry_i, cum_usd=cum_usd,
            mfe=mfe, mae=mae, mfe_usd=mfe * mult, mae_usd=mae * mult,
            # tuple form used for the equality check against port.trade_loop:
            _tuple=(direction, entry_px, exit_px, pts, usd),
        ))

    for i in range(n):
        cm = ctmin[i]
        gap_edge = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        session_flat = (900 <= cm < 960) or (block_ny and 510 <= cm < 540) \
            or (block_ln and 120 <= cm < 150) or gap_edge
        closed_this_bar = False
        reversed_this_bar = False
        exit_event = None   # (reason, exit_px) for the frame, if a trade closed on bar i
        # keep-hours entry gate: new entries only when this bar's London hour is in keep_hours.
        hour_ok = (ldn_hour is None) or (ldn_hour[i] in keep_hours)

        # fold THIS bar's high/low into the running MFE/MAE extremes BEFORE any close is recorded,
        # so a trade that exits on bar i counts bar i's excursion.
        _excursion_extend(i)

        # OPPOSITE signal = close AND REVERSE (identical to port.trade_loop). With keep-hours, the
        # close still happens but the reopen only fires if this bar's hour is allowed; otherwise the
        # trade just closes (reason "opphours") and we stay flat.
        if pos > 0 and short_sig[i] and not session_flat:
            record_trade(1, close[i], i, "opposite")
            exit_event = ("opposite", close[i])
            if hour_ok:
                pos = -1; entry_px = close[i]; best = low[i]; entry_i = i
                init_stop = (fext_short[i] + stop_buf) if fext_short[i] is not None else None
                reversed_this_bar = True
                mfe_px = low[i]; mae_px = high[i]     # new short: reset excursions to this bar
            else:
                pos = 0; entry_px = init_stop = best = None; entry_i = None; closed_this_bar = True
        elif pos < 0 and long_sig[i] and not session_flat:
            record_trade(-1, close[i], i, "opposite")
            exit_event = ("opposite", close[i])
            if hour_ok:
                pos = 1; entry_px = close[i]; best = high[i]; entry_i = i
                init_stop = (fext_long[i] - stop_buf) if fext_long[i] is not None else None
                reversed_this_bar = True
                mfe_px = high[i]; mae_px = low[i]      # new long: reset excursions to this bar
            else:
                pos = 0; entry_px = init_stop = best = None; entry_i = None; closed_this_bar = True

        if not reversed_this_bar and pos > 0 and (enable_trail or enable_init):
            best = max(best, high[i])
            sl = None
            if enable_init:
                sl = init_stop
            if enable_trail:
                t = best - trail
                sl = t if sl is None else max(sl, t)
            if sl is not None and low[i] <= sl:
                record_trade(1, sl, i, "stop")
                exit_event = ("stop", sl)
                pos = 0; entry_px = init_stop = best = None; entry_i = None
                closed_this_bar = True
        elif not reversed_this_bar and pos < 0 and (enable_trail or enable_init):
            best = min(best, low[i])
            sl = None
            if enable_init:
                sl = init_stop
            if enable_trail:
                t = best + trail
                sl = t if sl is None else min(sl, t)
            if sl is not None and high[i] >= sl:
                record_trade(-1, sl, i, "stop")
                exit_event = ("stop", sl)
                pos = 0; entry_px = init_stop = best = None; entry_i = None
                closed_this_bar = True

        if session_flat and pos != 0:
            record_trade(pos, close[i], i, "session")
            exit_event = ("session", close[i])
            pos = 0; entry_px = init_stop = best = None; entry_i = None
            closed_this_bar = True

        entry_event = None   # (dir, entry_px) for the frame, if a trade opened on bar i (non-reverse)
        if pos == 0 and not session_flat and not closed_this_bar and not reversed_this_bar and hour_ok:
            if long_sig[i] and not short_sig[i]:
                pos = 1; entry_px = close[i]; best = high[i]; entry_i = i
                init_stop = (fext_long[i] - stop_buf) if fext_long[i] is not None else None
                entry_event = (1, close[i])
                mfe_px = high[i]; mae_px = low[i]
            elif short_sig[i] and not long_sig[i]:
                pos = -1; entry_px = close[i]; best = low[i]; entry_i = i
                init_stop = (fext_short[i] + stop_buf) if fext_short[i] is not None else None
                entry_event = (-1, close[i])
                mfe_px = low[i]; mae_px = high[i]

        # active stop level to draw (after all position updates this bar)
        stop_level = None
        stop_kind = None
        if pos != 0 and (enable_trail or enable_init):
            if pos > 0:
                lv = None
                if enable_init:
                    lv = init_stop
                if enable_trail:
                    tt = best - trail
                    lv = tt if lv is None else max(lv, tt)
                stop_level = lv
            else:
                lv = None
                if enable_init:
                    lv = init_stop
                if enable_trail:
                    tt = best + trail
                    lv = tt if lv is None else min(lv, tt)
                stop_level = lv
            stop_kind = "trail" if enable_trail else "init"

        unreal = None
        if pos != 0 and entry_px is not None:
            unreal = ((close[i] - entry_px) if pos > 0 else (entry_px - close[i])) * mult

        frames[i] = dict(
            i=i, time=_ct_iso(epoch[i]),
            o=bars[i][1], h=high[i], l=low[i], c=close[i],
            res=res_line[i], supp=supp_line[i],
            run=pine_run[i], r2=pine_r2[i],
            long_sig=long_sig[i], short_sig=short_sig[i],
            long_arm=long_arm[i], short_arm=short_arm[i],
            entry=entry_event, exit=exit_event,
            pos=pos, entry_px=entry_px if pos != 0 else None,
            stop_level=stop_level, stop_kind=stop_kind,
            cum_usd=cum_usd, unreal_usd=unreal,
        )

    if pos != 0:
        record_trade(pos, close[-1], n - 1, "open")
        # annotate the final frame's exit (position was open through the last bar)
        frames[n - 1]["exit"] = ("open", close[-1])

    return frames, trades


def verify_matches(bars, sig, trades, **cfg):
    """Re-run the REAL port.trade_loop with the same config and assert the extracted trade tuples
    are identical. This is the acceptance test: recording must not change engine behaviour."""
    ref = port.trade_loop(bars, sig, **cfg)
    got = [t["_tuple"] for t in trades]
    if len(ref) != len(got):
        return False, f"count mismatch: port={len(ref)} frames={len(got)}"
    for k, (a, b) in enumerate(zip(ref, got)):
        # compare with a tiny float tolerance
        if a[0] != b[0] or any(abs(x - y) > 1e-6 for x, y in zip(a[1:], b[1:])):
            return False, f"trade #{k} mismatch: port={a} frames={b}"
    return True, f"exact match on {len(ref)} trades"


def write_parquet(frames, trades, meta, out_path, rows_per_group=1440):
    """Write frames as a COLUMNAR parquet table (each field its own column) with row groups sized
    to ~a trading day of 1-min bars (1440). Parquet stores per-row-group min/max stats for `i` and
    `time`, so a date-range read skips non-overlapping groups without decompressing them -- this is
    the sliceability JSON can't give. Tuple fields (entry/exit) are flattened to scalar columns.

    trades + meta ride along as a tiny parquet key-value metadata blob (JSON), so one file is the
    whole run. dict-decode of a column is cheap; ZSTD compresses the mostly-flat columns hard."""
    n = len(frames)
    cols = {
        "i": [f["i"] for f in frames],
        "time": [f["time"] for f in frames],
        "o": [f["o"] for f in frames], "h": [f["h"] for f in frames],
        "l": [f["l"] for f in frames], "c": [f["c"] for f in frames],
        "res": [f["res"] for f in frames], "supp": [f["supp"] for f in frames],
        # open_drive carries the RTH-open anchor alongside its two trigger rails; other strategies
        # do not emit it, so default to None rather than KeyError.
        "anchor": [f.get("anchor") for f in frames],
        "run": [f["run"] for f in frames], "r2": [f["r2"] for f in frames],
        "long_sig": [f["long_sig"] for f in frames],
        "short_sig": [f["short_sig"] for f in frames],
        "long_arm": [f["long_arm"] for f in frames],
        "short_arm": [f["short_arm"] for f in frames],
        "pos": [f["pos"] for f in frames],
        "entry_px": [f["entry_px"] for f in frames],
        "stop_level": [f["stop_level"] for f in frames],
        "stop_kind": [f["stop_kind"] for f in frames],
        "cum_usd": [f["cum_usd"] for f in frames],
        "unreal_usd": [f["unreal_usd"] for f in frames],
        # flatten entry=(dir,px) / exit=(reason,px) into scalar columns (null when no event)
        "entry_dir": [f["entry"][0] if f["entry"] else None for f in frames],
        "exit_reason": [f["exit"][0] if f["exit"] else None for f in frames],
        "exit_px": [f["exit"][1] if f["exit"] else None for f in frames],
    }
    schema = pa.schema([
        ("i", pa.int32()), ("time", pa.string()),
        ("o", pa.float64()), ("h", pa.float64()), ("l", pa.float64()), ("c", pa.float64()),
        ("res", pa.float64()), ("supp", pa.float64()), ("anchor", pa.float64()),
        ("run", pa.float64()), ("r2", pa.float64()),
        ("long_sig", pa.bool_()), ("short_sig", pa.bool_()),
        ("long_arm", pa.bool_()), ("short_arm", pa.bool_()),
        ("pos", pa.int8()), ("entry_px", pa.float64()),
        ("stop_level", pa.float64()), ("stop_kind", pa.string()),
        ("cum_usd", pa.float64()), ("unreal_usd", pa.float64()),
        ("entry_dir", pa.int8()), ("exit_reason", pa.string()), ("exit_px", pa.float64()),
    ])
    table = pa.table(cols, schema=schema)
    kv = {b"meta": json.dumps(meta).encode(), b"trades": json.dumps(trades).encode()}
    table = table.replace_schema_metadata(kv)
    pq.write_table(table, out_path, compression="zstd", compression_level=9,
                   row_group_size=rows_per_group, use_dictionary=["stop_kind", "exit_reason"])
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="csv path (default 5yr)")
    ap.add_argument("--oos", action="store_true", help="use the OOS Downloads/data.csv")
    ap.add_argument("--trail", type=float, default=None, help="enable trailing stop at N pts")
    ap.add_argument("--stop-buf", type=float, default=None, help="enable init stop, buffer N pts")
    ap.add_argument("--no-ny", action="store_true", help="disable NY-open block")
    ap.add_argument("--no-ln", action="store_true", help="disable London-open block")
    ap.add_argument("--out", default=None, help="output path (extension sets format; default parquet)")
    ap.add_argument("--json", action="store_true", help="also write a .json (debug/inspection)")
    ap.add_argument("--keep-hours", default=None,
                    help="comma list of LONDON hours to allow entries (e.g. 8,9,15,16,18); others blocked")
    a = ap.parse_args()
    keep_hours = set(int(x) for x in a.keep_hours.split(",")) if a.keep_hours else None

    path = port.OOS if a.oos else (a.file or port.FIVE_YR)
    tag = "oos" if a.oos else (os.path.splitext(os.path.basename(path))[0])

    cfg = dict(
        # detector params (from the port constants) -- recorded so each run self-documents
        win_len=port.WIN_LEN, run_min=port.RUN_MIN, min_r2=port.MIN_R2,
        pullback=port.PULLBACK, break_tol=port.BREAK_TOL, sr_half=port.SR_HALF,
        # trade-loop params
        block_ny=not a.no_ny, block_ln=not a.no_ln, mult=2.0,
        enable_trail=a.trail is not None, trail=(a.trail if a.trail is not None else port.TRAIL),
        enable_init=a.stop_buf is not None, stop_buf=(a.stop_buf if a.stop_buf is not None else port.STOP_BUF),
        keep_hours=sorted(keep_hours) if keep_hours else None,
    )

    # split cfg: detector keys are metadata-only; only trade-loop keys go to build_frames/trade_loop
    trade_keys = ("block_ny", "block_ln", "mult", "enable_trail", "trail", "enable_init", "stop_buf")
    trade_cfg = {k: cfg[k] for k in trade_keys}

    print(f"loading {path} ...")
    bars = port.load(path)
    print(f"  {len(bars)} bars")
    # fidelity flag: did the CSV carry Pine's exact S/R + ols columns (bar-exact), or were they
    # recomputed (directionally faithful)? -- exactly the badge the plan calls for.
    exact = any(b[6] is not None for b in bars) and any(b[8] is not None for b in bars)
    print(f"  fidelity: {'EXACT (Pine S/R+ols present)' if exact else 'RECOMPUTED (raw csv)'}")
    print("detecting signals (the slow step) ...")
    long_sig, short_sig, fext_long, fext_short, long_arm, short_arm = port.detect(
        bars, cfg["win_len"], cfg["run_min"], cfg["min_r2"],
        cfg["pullback"], cfg["break_tol"], cfg["sr_half"], return_arms=True)
    sig = (long_sig, short_sig, fext_long, fext_short)     # the 4-tuple trade_loop/verify expect
    arms = (long_arm, short_arm)                            # extra: the red/green arm-dot events

    print(f"building frames  trade_cfg={trade_cfg}  keep_hours={sorted(keep_hours) if keep_hours else None}")
    frames, trades = build_frames(bars, sig, arms=arms, keep_hours=keep_hours, **trade_cfg)

    if keep_hours:
        # keep-hours diverges from port.trade_loop by design -> strict verify doesn't apply.
        print(f"VERIFY: SKIPPED (keep_hours active; {len(trades)} trades)")
    else:
        ok, msg = verify_matches(bars, sig, trades, **trade_cfg)
        print(f"VERIFY: {'OK' if ok else 'FAIL'} -- {msg}")
        if not ok:
            sys.exit(1)

    st = port.stats([t["_tuple"] for t in trades])
    print(f"STATS : trades={st['n']}  net={st['net']:.1f}pt  ${st['usd']:.1f}  "
          f"win%={st['wr']:.1f}  PF={st['pf']:.2f}")

    for t in trades:
        del t["_tuple"]
    meta = dict(file=path, tag=tag, n_bars=len(bars), cfg=cfg, stats=st, exact=exact)
    here = os.path.dirname(__file__)

    if a.json or not _HAVE_ARROW:
        outj = os.path.join(here, f"run_{tag}.json")
        with open(outj, "w") as fh:
            json.dump(dict(meta=meta, trades=trades, frames=frames), fh)
        print(f"WROTE : {outj}  ({os.path.getsize(outj)/1e6:.1f} MB JSON)")

    if _HAVE_ARROW:
        outp = a.out or os.path.join(here, f"run_{tag}.parquet")
        write_parquet(frames, trades, meta, outp)
        print(f"WROTE : {outp}  ({os.path.getsize(outp)/1e6:.1f} MB parquet, "
              f"{len(frames)} frames, {len(trades)} trades)")
    elif not a.json:
        print("NOTE  : pyarrow not installed; wrote JSON only. `pip install pyarrow` for parquet.")


if __name__ == "__main__":
    main()
