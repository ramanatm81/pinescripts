#!/usr/bin/env python3
"""Export a Window-Displacement-Fade run into the replay-UI parquet schema.

Reuses replay_tool.frames_export.write_parquet (same columns the frontend reads). The strategy
logic mirrors the VALIDATED port backtest/window_displacement_fade_bt.py: same-bar entry on close,
anchor resets on trade close / session / first bar, fixed TP/SL bracket, prev-window pullback filter.
Fills the slope-specific columns (res/supp/run/r2/arms/stop_level) with nulls so the UI still renders.

USAGE
  .venv/bin/python wdf_export.py --oos --out run_wdf_oos.parquet
  .venv/bin/python wdf_export.py --out run_wdf_5yr.parquet          # full 5yr (slow load)
  .venv/bin/python wdf_export.py --thr 130 --tp 70 --sl 50 --prev-thr 0 --out run_wdf_5yr.parquet
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest"))
import window_displacement_fade_bt as port
import frames_export as fx


def build(bars, win_len, thr, tp, sl, prev_block, prev_win, prev_thr,
          block_ny, block_ln, mult=2.0):
    cm = [b[0] for b in bars]; high = [b[2] for b in bars]
    low = [b[3] for b in bars]; close = [b[4] for b in bars]; ep = [b[5] for b in bars]
    n = len(bars)
    pos = 0; entry_px = None; entry_i = None; anchor = 0; cum = 0.0
    mfe_px = mae_px = None
    frames = [None] * n; trades = []

    def rec(direction, exit_px, exit_i, reason):
        nonlocal cum
        pts = (exit_px - entry_px) if direction > 0 else (entry_px - exit_px)
        usd = pts * mult; cum += usd
        if direction > 0:
            mfe = (mfe_px - entry_px) if mfe_px is not None else 0.0
            mae = (mae_px - entry_px) if mae_px is not None else 0.0
        else:
            mfe = (entry_px - mfe_px) if mfe_px is not None else 0.0
            mae = (entry_px - mae_px) if mae_px is not None else 0.0
        trades.append(dict(dir=direction, entry_i=entry_i, entry_time=fx._ct_iso(ep[entry_i]),
                           entry_px=entry_px, exit_i=exit_i, exit_time=fx._ct_iso(ep[exit_i]),
                           exit_px=exit_px, pts=pts, usd=usd, reason=reason,
                           bars_held=exit_i - entry_i, cum_usd=cum,
                           mfe=mfe, mae=mae, mfe_usd=mfe * mult, mae_usd=mae * mult))

    for i in range(n):
        gap = i > 0 and (ep[i] - ep[i - 1]) / 60.0 > 60
        sess = (900 <= cm[i] < 960) or (block_ny and 510 <= cm[i] < 540) \
            or (block_ln and 120 <= cm[i] < 150) or gap
        closed = False; exit_event = None; entry_event = None

        if pos != 0:                       # fold this bar's excursion before any close
            if pos > 0:
                mfe_px = high[i] if mfe_px is None else max(mfe_px, high[i])
                mae_px = low[i] if mae_px is None else min(mae_px, low[i])
            else:
                mfe_px = low[i] if mfe_px is None else min(mfe_px, low[i])
                mae_px = high[i] if mae_px is None else max(mae_px, high[i])

        if pos > 0:
            if sess:
                rec(1, close[i], i, "session"); exit_event = ("session", close[i]); pos = 0; closed = True
            elif low[i] <= entry_px - sl:
                rec(1, entry_px - sl, i, "stop"); exit_event = ("stop", entry_px - sl); pos = 0; closed = True
            elif high[i] >= entry_px + tp:
                rec(1, entry_px + tp, i, "tp"); exit_event = ("tp", entry_px + tp); pos = 0; closed = True
        elif pos < 0:
            if sess:
                rec(-1, close[i], i, "session"); exit_event = ("session", close[i]); pos = 0; closed = True
            elif high[i] >= entry_px + sl:
                rec(-1, entry_px + sl, i, "stop"); exit_event = ("stop", entry_px + sl); pos = 0; closed = True
            elif low[i] <= entry_px - tp:
                rec(-1, entry_px - tp, i, "tp"); exit_event = ("tp", entry_px - tp); pos = 0; closed = True
        if closed:
            entry_px = entry_i = None; mfe_px = mae_px = None

        reset = (i == 0) or sess or closed
        if reset:
            anchor = i
        bs = i - anchor
        lookback = min(win_len, bs)
        disp = (close[i] - close[i - lookback]) if bs >= 1 else None
        long_sig = disp is not None and disp <= -thr
        short_sig = disp is not None and disp >= thr
        prev_avail = i >= lookback + prev_win
        pm = (close[i - lookback] - close[i - lookback - prev_win]) if prev_avail else None
        long_ok = long_sig and (not prev_block or (pm is not None and pm > prev_thr))
        short_ok = short_sig and (not prev_block or (pm is not None and pm < -prev_thr))

        if pos == 0 and not sess:
            if long_ok and not short_ok:
                pos = 1; entry_px = close[i]; entry_i = i; entry_event = (1, close[i])
                mfe_px = high[i]; mae_px = low[i]
            elif short_ok and not long_ok:
                pos = -1; entry_px = close[i]; entry_i = i; entry_event = (-1, close[i])
                mfe_px = low[i]; mae_px = high[i]

        unreal = (((close[i] - entry_px) if pos > 0 else (entry_px - close[i])) * mult) if pos != 0 else None
        frames[i] = dict(i=i, time=fx._ct_iso(ep[i]), o=bars[i][1], h=high[i], l=low[i], c=close[i],
                         res=None, supp=None, run=disp, r2=None,
                         long_sig=long_sig, short_sig=short_sig, long_arm=False, short_arm=False,
                         entry=entry_event, exit=exit_event, pos=pos,
                         entry_px=entry_px if pos != 0 else None,
                         stop_level=None, stop_kind=None, cum_usd=cum, unreal_usd=unreal)

    if pos != 0:
        rec(pos, close[-1], n - 1, "open")
        frames[n - 1]["exit"] = ("open", close[-1])
    return frames, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--oos", action="store_true")
    ap.add_argument("--thr", type=float, default=port.THR)
    ap.add_argument("--tp", type=float, default=port.TP)
    ap.add_argument("--sl", type=float, default=port.SL)
    ap.add_argument("--prev-thr", type=float, default=port.PREV_THR)
    ap.add_argument("--prev-win", type=int, default=port.PREV_WIN)
    ap.add_argument("--win-len", type=int, default=port.WIN_LEN)
    ap.add_argument("--no-prev", action="store_true")
    ap.add_argument("--no-ny", action="store_true"); ap.add_argument("--no-ln", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    path = port.OOS if a.oos else (a.file or port.FIVE_YR)
    tag = a.out[len("run_"):-len(".parquet")] if a.out and a.out.startswith("run_") else ("wdf_oos" if a.oos else "wdf_5yr")
    print(f"loading {path} ...")
    bars = port.load(path)
    print(f"  {len(bars)} bars")
    prev_block = not a.no_prev
    frames, trades = build(bars, a.win_len, a.thr, a.tp, a.sl, prev_block, a.prev_win, a.prev_thr,
                           not a.no_ny, not a.no_ln)
    net = sum(t["pts"] for t in trades); wins = sum(1 for t in trades if t["pts"] > 0)
    n = len(trades)
    st = dict(n=n, net=net, usd=net * 2.0, wr=100.0 * wins / n if n else 0.0,
              wins=wins, losses=n - wins,
              pf=(sum(t["pts"] for t in trades if t["pts"] > 0) /
                  -sum(t["pts"] for t in trades if t["pts"] <= 0)) if (n - wins) else float("inf"))
    print(f"STATS : trades={n} net={net:.0f}pt ${net*2:.0f} win%={st['wr']:.1f} PF={st['pf']:.2f}")
    cfg = dict(strategy="window_displacement_fade", win_len=a.win_len, thr=a.thr, tp=a.tp, sl=a.sl,
               prev_block=prev_block, prev_win=a.prev_win, prev_thr=a.prev_thr,
               block_ny=not a.no_ny, block_ln=not a.no_ln, mult=2.0)
    meta = dict(file=path, tag=tag, n_bars=len(bars), cfg=cfg, stats=st, exact=False)
    here = os.path.dirname(__file__)
    outp = a.out or os.path.join(here, f"run_{tag}.parquet")
    if not os.path.isabs(outp):
        outp = os.path.join(here, outp)
    fx.write_parquet(frames, trades, meta, outp)
    print(f"WROTE : {outp}  ({os.path.getsize(outp)/1e6:.1f} MB, {len(frames)} frames, {n} trades)")


if __name__ == "__main__":
    main()
