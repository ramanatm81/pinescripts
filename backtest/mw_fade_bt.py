#!/usr/bin/env python3
"""
M/W FADE after an open-drive run ("Fukui") -- a SEPARATE strategy, not an exit rule.

The open-drive move only supplies CONTEXT. The trade is the fade of a chart-pattern top/bottom
that forms once that move has run and started giving back.

  1 CONTEXT : price breaks the OPENING RANGE (high/low of the first or_minutes after 08:30 CT) by
              more than break_pts. Direction of that break = the context direction. No position is
              taken on the break itself -- it only marks the day as "in play" and sets the side.
  2 RUN     : the break must actually work -- it has to reach mfe_min points beyond the OR edge.
  3 GIVEBACK: price must then retrace more than giveback_pts (ABSOLUTE POINTS, not a fraction).
  4 PATTERN : an M (after an UP break -> we will fade SHORT) or a W (after a DOWN break -> fade
              LONG). The pattern side and the fade side are locked together: M is only ever traded
              short, W only ever long. Found from FRACTAL PIVOTS:
                 P1 = pivot high, V = pivot low (the neckline), P2 = pivot high
                 strictly ordered P1 < V < P2 in time, |P2 - P1| <= peak_tol,
                 and both peaks at least neck_min points above V (a real M, not a flat wiggle).
  5 ENTRY   : a bar CLOSES through the neckline V -> enter the FADE (short after an M, long after
              a W). One fade per day.
  6 EXIT    : exit_mode 0 = fixed TP/SL, 1 = EOD-hold, 2 = ATR stop + EOD, 3 = TP/SL + ATR stop.

PIVOTS ARE CAUSAL. A fractal pivot at bar k needs piv_n bars on BOTH sides, so it is only KNOWN at
bar k+piv_n. Every pattern test uses pivots confirmed at or before the current bar -- the detector
never sees a peak it could not have seen live. Getting this wrong is the classic way a pattern
backtest invents an edge that does not exist.

Timestamps normalized to America/Chicago (DST-aware). Fills: entry at the breaking bar's close;
stops/TP checked intrabar against high/low and filled at the level.

USAGE
  python3 mw_fade_bt.py                # default config, 5yr + OOS
  python3 mw_fade_bt.py --sweep        # exit-mode / threshold grid
  python3 mw_fade_bt.py --dump out.csv # per-trade csv incl. the P1/V/P2 geometry
"""
import csv
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

FIVE_YR = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
OOS = "/Users/maheshk81/Downloads/data.csv"

CT = ZoneInfo("America/Chicago")
LDN = ZoneInfo("Europe/London")
RTH_OPEN_MIN = 510   # 08:30 CT
EOD_MIN = 900        # 15:00 CT


def load(path):
    bars = []
    with open(path, newline="") as fh:
        r = csv.reader(fh)
        header = next(r)
        idx = {name: i for i, name in enumerate(header)}
        ci = {k: idx.get(k) for k in ("time", "open", "high", "low", "close")}
        for row in r:
            try:
                dt = datetime.fromisoformat(row[ci["time"]])
                ct = dt.astimezone(CT)
                bars.append((ct.hour * 60 + ct.minute,
                             float(row[ci["open"]]), float(row[ci["high"]]),
                             float(row[ci["low"]]), float(row[ci["close"]]),
                             dt.timestamp()))
            except (ValueError, TypeError, IndexError, KeyError):
                continue
    return bars


def _daily_atr(bars, ndays=14):
    dh = {}; dl = {}; order = []
    for ctmin, o, h, lo, c, epoch in bars:
        d = datetime.fromtimestamp(epoch, CT).date()
        if d not in dh:
            dh[d] = h; dl[d] = lo; order.append(d)
        else:
            dh[d] = max(dh[d], h); dl[d] = min(dl[d], lo)
    rng = {d: dh[d] - dl[d] for d in order}
    atr = {}
    for i, d in enumerate(order):
        prior = order[max(0, i - ndays):i]
        atr[d] = (sum(rng[p] for p in prior) / len(prior)) if len(prior) >= ndays else None
    return atr


def _pivots(bars, lo_i, hi_i, piv_n):
    """Fractal pivots inside [lo_i, hi_i). Returns (highs, lows) as lists of
    (bar_index, price, confirmed_at_index). A pivot high at k is a bar whose high is >= every high
    in [k-piv_n, k+piv_n]; it is only KNOWN at k+piv_n, which is what confirmed_at records."""
    ph = []; pl = []
    for k in range(lo_i + piv_n, hi_i - piv_n):
        hk = bars[k][2]; lk = bars[k][3]
        is_h = True; is_l = True
        for m in range(k - piv_n, k + piv_n + 1):
            if m == k:
                continue
            if bars[m][2] >= hk:
                is_h = False
            if bars[m][3] <= lk:
                is_l = False
            if not is_h and not is_l:
                break
        if is_h:
            ph.append((k, hk, k + piv_n))
        if is_l:
            pl.append((k, lk, k + piv_n))
    return ph, pl


def run(bars, or_minutes=30, break_pts=20.0, mfe_min=60.0, giveback_pts=40.0,
        piv_n=5, peak_tol=15.0, neck_min=25.0, pattern_max_bars=180,
        exit_mode=0, tp_pts=80.0, sl_pts=60.0, sl_mult=1.0, atr_days=14,
        entry_end_min=360, slip=2.0, enable_long=True, enable_short=True):
    """Returns list of trades (dir, entry_px, exit_px, pts, entry_epoch, reason, info)."""
    trades = []
    n = len(bars)
    atr = _daily_atr(bars, atr_days)

    # ---- group bar indices by session day ----
    days = {}
    prev_ms = None
    for i in range(n):
        ctmin, o, h, lo, c, epoch = bars[i]
        d = datetime.fromtimestamp(epoch, CT).date()
        days.setdefault(d, []).append(i)

    for d, idxs in sorted(days.items()):
        rth = [i for i in idxs if 0 <= bars[i][0] - RTH_OPEN_MIN and bars[i][0] < EOD_MIN]
        if len(rth) < 60:
            continue
        a_atr = atr.get(d)

        # ---- 0. the OPENING RANGE: high/low of the first or_minutes after the open ----
        or_bars = [i for i in rth if (bars[i][0] - RTH_OPEN_MIN) < or_minutes]
        if not or_bars:
            continue
        or_hi = max(bars[i][2] for i in or_bars)
        or_lo = min(bars[i][3] for i in or_bars)
        anchor = bars[rth[0]][1]

        # ---- 1. context: price breaks an OR edge by more than break_pts ----
        ctx_i = None; ctx_dir = 0
        for i in rth:
            if (bars[i][0] - RTH_OPEN_MIN) < or_minutes:
                continue
            if bars[i][2] >= or_hi + break_pts:
                ctx_i, ctx_dir = i, 1; break
            if bars[i][3] <= or_lo - break_pts:
                ctx_i, ctx_dir = i, -1; break
        if ctx_i is None:
            continue

        # ---- 2. run: the break must reach mfe_min beyond the OR EDGE it broke ----
        trig_px = (or_hi + break_pts) if ctx_dir > 0 else (or_lo - break_pts)
        run_ext = None; run_i = None
        for i in rth:
            if i <= ctx_i:
                continue
            ext = bars[i][2] if ctx_dir > 0 else bars[i][3]
            if run_ext is None or ((ext > run_ext) if ctx_dir > 0 else (ext < run_ext)):
                run_ext = ext; run_i = i
        if run_ext is None:
            continue
        mfe = (run_ext - trig_px) * ctx_dir
        if mfe < mfe_min:
            continue

        # ---- pivots for the day, causal ----
        ph, pl = _pivots(bars, rth[0], rth[-1] + 1, piv_n)
        peaks = ph if ctx_dir > 0 else pl          # M uses highs, W uses lows
        necks = pl if ctx_dir > 0 else ph

        # ---- 3+4. walk bars forward; at each bar use ONLY pivots confirmed by then ----
        pos = 0; entry_px = None; entry_i = None; stop = None; targ = None
        info = None
        took = False
        for i in rth:
            if i <= ctx_i or bars[i][0] >= EOD_MIN:
                continue
            # manage an open fade
            if pos != 0:
                h, lo, c = bars[i][2], bars[i][3], bars[i][4]
                done = False
                if stop is not None:
                    if pos > 0 and lo <= stop:
                        trades.append((pos, entry_px, stop, (stop - entry_px) - slip,
                                       bars[entry_i][5], "stop", info)); pos = 0; done = True
                    elif pos < 0 and h >= stop:
                        trades.append((pos, entry_px, stop, (entry_px - stop) - slip,
                                       bars[entry_i][5], "stop", info)); pos = 0; done = True
                if not done and targ is not None:
                    if pos > 0 and h >= targ:
                        trades.append((pos, entry_px, targ, (targ - entry_px) - slip,
                                       bars[entry_i][5], "tp", info)); pos = 0; done = True
                    elif pos < 0 and lo <= targ:
                        trades.append((pos, entry_px, targ, (entry_px - targ) - slip,
                                       bars[entry_i][5], "tp", info)); pos = 0; done = True
                if not done and i == rth[-1]:
                    c2 = bars[i][4]
                    pts = (c2 - entry_px) if pos > 0 else (entry_px - c2)
                    trades.append((pos, entry_px, c2, pts - slip, bars[entry_i][5],
                                   "session", info)); pos = 0
                continue
            if took or (bars[i][0] - RTH_OPEN_MIN) >= entry_end_min:
                continue

            # giveback so far, in POINTS, measured from the best extreme seen up to bar i
            best = None
            for k in rth:
                if k > i:
                    break
                if k <= ctx_i:
                    continue
                e = bars[k][2] if ctx_dir > 0 else bars[k][3]
                if best is None or ((e > best) if ctx_dir > 0 else (e < best)):
                    best = e
            if best is None:
                continue
            if (best - trig_px) * ctx_dir < mfe_min:
                continue
            cur = bars[i][4]
            gb = (best - cur) * ctx_dir
            if gb <= giveback_pts:
                continue

            # pattern: P1, V, P2 all CONFIRMED by bar i, strictly ordered, in the run region
            pk = [p for p in peaks if p[2] <= i and p[0] > ctx_i and (i - p[0]) <= pattern_max_bars]
            nk = [v for v in necks if v[2] <= i and v[0] > ctx_i]
            if len(pk) < 2 or not nk:
                continue
            p2 = pk[-1]; p1 = None
            for cand in reversed(pk[:-1]):
                if abs(cand[1] - p2[1]) <= peak_tol:
                    p1 = cand; break
            if p1 is None:
                continue
            mid = [v for v in nk if p1[0] < v[0] < p2[0]]
            if not mid:
                continue
            # the neckline = the deepest pivot between the two peaks
            v = min(mid, key=lambda x: x[1]) if ctx_dir > 0 else max(mid, key=lambda x: x[1])
            depth1 = (p1[1] - v[1]) * ctx_dir
            depth2 = (p2[1] - v[1]) * ctx_dir
            if depth1 < neck_min or depth2 < neck_min:
                continue
            # 5. ENTRY: this bar closes THROUGH the neckline, away from the peaks
            brk = (cur < v[1]) if ctx_dir > 0 else (cur > v[1])
            if not brk:
                continue
            fdir = -ctx_dir                      # fade the drive
            if fdir > 0 and not enable_long:
                continue
            if fdir < 0 and not enable_short:
                continue
            pos = fdir; entry_px = cur; entry_i = i; took = True
            if exit_mode == 0:
                stop = entry_px - sl_pts * fdir; targ = entry_px + tp_pts * fdir
            elif exit_mode == 1:
                stop = None; targ = None
            elif exit_mode == 2:
                stop = (entry_px - sl_mult * a_atr * fdir) if a_atr else None; targ = None
            else:
                s1 = entry_px - sl_pts * fdir
                s2 = (entry_px - sl_mult * a_atr * fdir) if a_atr else None
                stop = s1 if s2 is None else (max(s1, s2) if fdir > 0 else min(s1, s2))
                targ = entry_px + tp_pts * fdir
            info = dict(day=d.isoformat(), ctx_dir=ctx_dir, anchor=anchor,
                        or_hi=or_hi, or_lo=or_lo, or_width=round(or_hi - or_lo, 2),
                        trig_px=trig_px,
                        mfe=mfe, giveback=gb, p1_i=p1[0], p1=p1[1], v_i=v[0], v=v[1],
                        p2_i=p2[0], p2=p2[1], peak_gap=abs(p2[1] - p1[1]),
                        depth=min(depth1, depth2), bars_p1_p2=p2[0] - p1[0],
                        entry_ldn=datetime.fromtimestamp(bars[i][5], LDN).strftime("%H:%M"))
        # end-of-day flatten for a fade still open
        if pos != 0:
            c2 = bars[rth[-1]][4]
            pts = (c2 - entry_px) if pos > 0 else (entry_px - c2)
            trades.append((pos, entry_px, c2, pts - slip, bars[entry_i][5], "session", info))
    return trades


def summarize(trades):
    if not trades:
        return dict(n=0, net=0.0, extop10=0.0, wr=0.0, per_year={}, long_net=0.0, short_net=0.0,
                    top10_pct=0.0, pf=0.0)
    pts = sorted((t[3] for t in trades), reverse=True)
    net = sum(pts); top10 = sum(pts[:10])
    gp = sum(p for p in pts if p > 0); gl = -sum(p for p in pts if p <= 0)
    per_year = {}
    for t in trades:
        y = datetime.fromtimestamp(t[4], CT).year
        per_year[y] = per_year.get(y, 0.0) + t[3]
    return dict(n=len(trades), net=net, extop10=net - top10,
                wr=sum(1 for t in trades if t[3] > 0) / len(trades) * 100,
                per_year=per_year,
                long_net=sum(t[3] for t in trades if t[0] > 0),
                short_net=sum(t[3] for t in trades if t[0] < 0),
                top10_pct=(top10 / net * 100 if net else 0.0),
                pf=(gp / gl) if gl > 0 else float("inf"))


def fmt(tag, s):
    if not s["n"]:
        return f"{tag:30s} n=0"
    yrs = s["per_year"]
    pos = sum(1 for v in yrs.values() if v > 0)
    ys = " ".join(f"{y}:{int(v):+d}" for y, v in sorted(yrs.items()))
    return (f"{tag:30s} n={s['n']:4d} net={s['net']:+8.0f} exTop10={s['extop10']:+8.0f} "
            f"top10%={s['top10_pct']:5.0f} WR={s['wr']:4.1f}% PF={s['pf']:.2f} "
            f"L={s['long_net']:+7.0f} S={s['short_net']:+7.0f} yrs+={pos}/{len(yrs)}\n    {ys}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--dump")
    args = ap.parse_args()

    print("loading...")
    five = load(FIVE_YR)
    oos = load(OOS)
    print(f"5yr bars={len(five)}  OOS bars={len(oos)}")

    if args.dump:
        tr = run(five)
        with open(args.dump, "w", newline="") as fh:
            w = None
            for t in tr:
                row = dict(t[6]); row.update(dir=("long" if t[0] > 0 else "short"),
                                             entry_px=round(t[1], 2), exit_px=round(t[2], 2),
                                             pts=round(t[3], 1), reason=t[5])
                if w is None:
                    w = csv.DictWriter(fh, fieldnames=list(row.keys())); w.writeheader()
                w.writerow(row)
        print(f"dumped {len(tr)} trades -> {args.dump}")
    elif args.sweep:
        for em, lbl in ((0, "fixed TP/SL"), (1, "EOD-hold"), (2, "ATR stop + EOD"), (3, "TP/SL + ATR")):
            print(f"\n########## exit_mode={em} ({lbl}) ##########")
            for bp in (5, 20, 40):
                for mm in (40, 60, 80):
                    s = summarize(run(five, break_pts=bp, mfe_min=mm, giveback_pts=40, exit_mode=em))
                    print(fmt(f"  brk>{bp} mfe>={mm}", s))
    else:
        for em, lbl in ((0, "fixed TP80/SL60"), (1, "EOD-hold"), (2, "ATR stop + EOD")):
            print(f"\n=== exit_mode={em} ({lbl}) ===")
            print(fmt("5yr", summarize(run(five, exit_mode=em))))
            print(fmt("OOS", summarize(run(oos, exit_mode=em))))
