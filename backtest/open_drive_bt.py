#!/usr/bin/env python3
"""
Backtester for open_drive_strategy.pine ("Otaru") -- open-drive momentum.

Mirrors the .pine EXACTLY:
  ANCHOR  : RTH open price (open of the first bar at/after 08:30 CT). Frozen for the day.
  TRIGGER : resting STOP orders at anchor +/- trigPts, armed from settleMin to entryEndMin past
            the open. Whichever side price reaches first fills; the other is cancelled.
  ENTRY   : WITH the move (momentum), via a resting STOP order at open +/- trigPts.
  FILTER  : optional |pre-open slope| gate over 07:30-08:30 CT (60 min ending at the open).
  EXIT    : ATR stop (sl_mult * trailing daily ATR, frozen at entry) OR EOD flatten at 15:00 CT.
            No take-profit -- adding one costs net. A session gap also flattens.

FILL MODEL -- the thing that matters most here. A resting stop fills AT its level when a bar trades
through it, but at the bar's OPEN when the bar gaps past it (22.8% of entries on 5yr MNQ). Assuming
it always fills at the level inflates net ~2x (+24,188 vs +12,761 at 1pt slip). fillmode:
  'stop'  (default) -- level, or bar open on a gap-through. What TV does. Quote this one.
  'level'           -- always the level. WRONG, kept only to expose the inflation via --fillcheck.
  'close'           -- close of the triggering bar; a close-triggered entry, not what this ships.

Use a STOP, never a LIMIT: a buy limit at anchor+trigPts fills only when price trades DOWN into it,
i.e. exactly when the move fails, and never on the drive itself.

Timestamps normalized to America/Chicago via DST-aware ZoneInfo. A fixed -5 is wrong in winter and
silently shifts the session by an hour for ~40% of the year.

USAGE
  python3 open_drive_bt.py                 # default config, 5yr + OOS, 1 and 2pt slip
  python3 open_drive_bt.py --sweep         # trigger x slope-gate grid
  python3 open_drive_bt.py --fillcheck     # close-fill vs level-fill, the inflation gap
"""
import csv
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

FIVE_YR = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
OOS = "/Users/maheshk81/Downloads/data.csv"

CT = ZoneInfo("America/Chicago")
RTH_OPEN_MIN = 510   # 08:30 CT
EOD_MIN = 900        # 15:00 CT
PRE_LEN = 60         # pre-open slope window, minutes ending at the open
PRE_MIN_BARS = 55    # require a near-complete hour, same as the pine


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
    """Trailing mean of prior-day full ranges, keyed by Chicago date. PAST-ONLY: the ATR on day D is
    the mean of the ndays days strictly before D. Mirrors the pine's rolling-buffer ATR."""
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


def run(bars, trig_pts=120.0, settle_min=0, entry_end_min=330,
        use_slope_gate=False, slope_min=0.75,
        enable_long=True, enable_short=True, slip=1.0, fillmode="stop",
        use_atr_stop=True, sl_mult=1.0, atr_days=3):
    """Returns list of trades: (dir, entry_px, exit_px, pts, entry_epoch, reason)."""
    trades = []
    n = len(bars)
    atr = _daily_atr(bars, atr_days) if use_atr_stop else {}

    rth_open_px = None
    took_trade = False
    pre_first_close = None
    pre_slope = None
    pre_bars = 0
    pre_ready = False

    pos = 0
    entry_px = None
    entry_epoch = None
    stop_level = None

    prev_ms = None
    for i in range(n):
        ctmin, o, h, lo, c, epoch = bars[i]
        ms = ctmin - RTH_OPEN_MIN
        gap = (i > 0) and (epoch - bars[i - 1][5]) / 60.0 > 60
        eod = EOD_MIN <= ctmin < 960
        new_day = (ms == 0) or (prev_ms is not None and prev_ms < 0 <= ms) or gap

        if new_day:
            rth_open_px = None
            took_trade = False
            pre_first_close = None
            pre_bars = 0

        # ---- pre-open slope accumulation (07:30-08:30 CT) ----
        if -PRE_LEN <= ms < 0:
            if pre_first_close is None:
                pre_first_close = c
                pre_bars = 0
            pre_bars += 1
            pre_slope = (c - pre_first_close) / float(PRE_LEN)
            pre_ready = pre_bars >= PRE_MIN_BARS

        # ---- capture the RTH open anchor ----
        # Fixed 60-min grace, NOT tied to settle_min: with settle_min=0 a settle-tied window would
        # be empty and a missing 08:30 bar would silently skip the day. Mirrors the pine.
        if 0 <= ms < 60 and rth_open_px is None:
            rth_open_px = o

        # ---- ATR STOP (resting protective order, checked intrabar against this bar's H/L) ----
        # Checked BEFORE the session flatten: a stop that is hit during the day fills at the stop,
        # it does not wait for the close. Only from the bar AFTER entry -- on the entry bar the
        # protective order is placed, not yet resting (matches TV under process_orders_on_close).
        if pos != 0 and stop_level is not None and entry_epoch != epoch:
            if pos > 0 and lo <= stop_level:
                _exit(trades, pos, entry_px, stop_level, entry_epoch, "atrstop", slip)
                pos = 0
            elif pos < 0 and h >= stop_level:
                _exit(trades, pos, entry_px, stop_level, entry_epoch, "atrstop", slip)
                pos = 0

        # ---- EOD / gap flatten (before entries: never open and close on the same bar) ----
        if pos != 0 and (eod or gap):
            _exit(trades, pos, entry_px, c, entry_epoch, "session", slip)
            pos = 0

        # ---- entry ----
        in_window = settle_min <= ms < entry_end_min and not eod
        slope_ok = (not use_slope_gate) or (pre_ready and pre_slope is not None
                                            and abs(pre_slope) >= slope_min)
        if pos == 0 and in_window and not took_trade and slope_ok and rth_open_px is not None:
            up_lvl = rth_open_px + trig_pts
            dn_lvl = rth_open_px - trig_pts
            if fillmode == "close":
                up = c >= up_lvl
                dn = c <= dn_lvl
                fill_up = fill_dn = c
            elif fillmode == "level":
                # always-at-the-level: WRONG, ignores gap-throughs. --fillcheck only.
                up = h >= up_lvl
                dn = lo <= dn_lvl
                fill_up, fill_dn = up_lvl, dn_lvl
            else:
                # resting stop: the level, or the bar OPEN when the bar gapped past it
                up = h >= up_lvl
                dn = lo <= dn_lvl
                fill_up = max(o, up_lvl) if o > up_lvl else up_lvl
                fill_dn = min(o, dn_lvl) if o < dn_lvl else dn_lvl
            a = atr.get(datetime.fromtimestamp(epoch, CT).date()) if use_atr_stop else None
            if up and enable_long:
                pos = 1; entry_px = fill_up; entry_epoch = epoch; took_trade = True
                stop_level = (entry_px - sl_mult * a) if a else None
            elif dn and enable_short:
                pos = -1; entry_px = fill_dn; entry_epoch = epoch; took_trade = True
                stop_level = (entry_px + sl_mult * a) if a else None

        prev_ms = ms

    return trades


def _exit(trades, direction, e_px, x_px, e_epoch, reason, slip):
    pts = (x_px - e_px) if direction > 0 else (e_px - x_px)
    pts -= slip   # charge slippage once per round-trip
    trades.append((direction, e_px, x_px, pts, e_epoch, reason))


def summarize(trades):
    if not trades:
        return dict(n=0, net=0.0, extop10=0.0, wr=0.0, per_year={}, long_net=0.0,
                    short_net=0.0, top10_pct=0.0)
    pts = sorted((t[3] for t in trades), reverse=True)
    net = sum(pts)
    top10 = sum(pts[:10])
    per_year = {}
    for t in trades:
        y = datetime.fromtimestamp(t[4], CT).year
        per_year[y] = per_year.get(y, 0.0) + t[3]
    return dict(n=len(trades), net=net, extop10=net - top10,
                wr=sum(1 for t in trades if t[3] > 0) / len(trades) * 100,
                per_year=per_year,
                long_net=sum(t[3] for t in trades if t[0] > 0),
                short_net=sum(t[3] for t in trades if t[0] < 0),
                top10_pct=(top10 / net * 100 if net else 0.0))


def fmt(tag, s):
    if not s["n"]:
        return f"{tag:26s} n=0"
    yrs = s["per_year"]
    pos = sum(1 for v in yrs.values() if v > 0)
    ys = " ".join(f"{y}:{int(v):+d}" for y, v in sorted(yrs.items()))
    return (f"{tag:26s} n={s['n']:5d} net={s['net']:+9.0f} exTop10={s['extop10']:+8.0f} "
            f"top10%={s['top10_pct']:5.0f} WR={s['wr']:4.1f}% L={s['long_net']:+8.0f} "
            f"S={s['short_net']:+8.0f} yrs+={pos}/{len(yrs)}\n    {ys}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--fillcheck", action="store_true")
    args = ap.parse_args()

    print("loading...")
    five = load(FIVE_YR)
    oos = load(OOS)
    print(f"5yr bars={len(five)}  OOS bars={len(oos)}")

    if args.fillcheck:
        print("\n=== FILL MODEL: stop (real) vs level (inflated) vs close ===")
        for gate, smin in ((False, 0.0), (True, 0.75)):
            for trig in (100.0, 150.0):
                for fm in ("stop", "level", "close"):
                    tag = f"trig{int(trig)} gate={smin if gate else 'off'} {fm}"
                    print(fmt(tag, summarize(run(five, trig_pts=trig, use_slope_gate=gate,
                                                 slope_min=smin, fillmode=fm))))
    elif args.sweep:
        for slip in (0.0, 1.0):
            print(f"\n########## SLIP = {slip} ##########")
            for gate, smin in ((False, 0.0), (True, 0.5), (True, 0.75), (True, 1.0), (True, 1.5)):
                for trig in (100.0, 150.0, 200.0, 250.0):
                    tag = f"trig{int(trig)} gate={smin if gate else 'off'}"
                    print(fmt(tag, summarize(run(five, trig_pts=trig, use_slope_gate=gate,
                                                 slope_min=smin, slip=slip))))
    else:
        for slip in (1.0, 2.0):
            print(f"\n=== DEFAULT (trig120, gate OFF, stop-order fills, EOD-hold) slip={slip} ===")
            print(fmt("5yr", summarize(run(five, slip=slip))))
            print(fmt("OOS", summarize(run(oos, slip=slip))))
            print(f"\n=== trig100 (previous default) slip={slip} ===")
            print(fmt("5yr", summarize(run(five, trig_pts=100.0, slip=slip))))
            print(fmt("OOS", summarize(run(oos, trig_pts=100.0, slip=slip))))
            print(f"\n=== NO ATR STOP (the old default) slip={slip} ===")
            print(fmt("5yr", summarize(run(five, use_atr_stop=False, slip=slip))))
            print(fmt("OOS", summarize(run(oos, use_atr_stop=False, slip=slip))))
            print(f"\n=== SLOPE GATE ON (trig150, gate 0.75 -- NEGATIVE exTop10) slip={slip} ===")
            print(fmt("5yr", summarize(run(five, trig_pts=150.0, use_slope_gate=True, slip=slip))))
            print(fmt("OOS", summarize(run(oos, trig_pts=150.0, use_slope_gate=True, slip=slip))))
