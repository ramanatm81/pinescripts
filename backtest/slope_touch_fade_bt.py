#!/usr/bin/env python3
"""
Backtester for slope_touch_fade_strategy.pine ("Nara").

Mirrors the .pine EXACTLY:
  DETECTOR : fixed-150 OLS run -> arm on S/R-line touch (break-tol) -> track extreme ->
             fire triangle on pullbackPts reversal -> re-entry lock.
  TRADE    : enter flat->pos on triangle (long fade at support / short at resistance),
             initial hard stop beyond the faded extreme, TRAILING stop by trailPts off best
             price, FLAT between trades.
  SESSION  : Chicago-time scaffolding from backtest.py --
               EOD flatten 900..960 (15:00-16:00 CT)      -- always, flatten + block
               NY open     510..540 (08:30-09:00 CT)      -- flatten + block (toggle)
               London open 120..150 (02:00-02:30 CT)      -- flatten + block (toggle)
             All three FLATTEN an open trade AND block new entries (the fade rule).

Timestamps in EVERY file are normalized to America/Chicago (dt.astimezone(UTC-5)), exactly
like backtest.py -- Pine uses hour(time,"America/Chicago").

USAGE
  python3 slope_touch_fade_bt.py            # runs 5yr + OOS at defaults
  python3 slope_touch_fade_bt.py --sweep    # sweeps trailPts x stopBufPts, both files

Slippage: 0 for now (per user). Fills on close (process_orders_on_close=true equivalent):
stops are checked intrabar against high/low; entries/exits priced at the triggering level.
"""
import csv
import argparse
from datetime import datetime, timezone, timedelta

FIVE_YR = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
OOS = "/Users/maheshk81/Downloads/data.csv"

# --- detector defaults (sync with slope_touch_fade_strategy.pine) ---
WIN_LEN = 150
RUN_MIN = 100.0
MIN_R2 = 0.75
PULLBACK = 70.0
BREAK_TOL = 5.0
SR_HALF = 10          # fractal half-width
# --- trade defaults ---
TRAIL = 80.0
STOP_BUF = 10.0
BLOCK_NY = True
BLOCK_LN = True

CT = timezone(timedelta(hours=-5))   # Chicago (CDT, matches backtest.py's fixed -5)


def load(path):
    """Read time,open,high,low,close from a CSV (extra columns ignored). Return list of
    (ct_minutes, o, h, l, c, epoch_sec). Normalizes every timestamp to Chicago like backtest.py;
    epoch_sec is kept so the trade loop can detect holiday/weekend GAPS (>60min between bars)."""
    bars = []
    with open(path, newline="") as fh:
        r = csv.reader(fh)
        header = next(r)
        # tolerate a corrupted first data cell / BOM; find columns by name
        idx = {name: i for i, name in enumerate(header)}
        ci = {k: idx.get(k) for k in ("time", "open", "high", "low", "close")}
        # If the file is a Pine STRATEGY export it also carries Pine's exact S/R lines -- use them
        # (my pivots() differs from ta.pivothigh at some bars; the exported columns are ground truth).
        res_col = idx.get("resistance (pivot high)")
        supp_col = idx.get("support (pivot low)")
        run_col = idx.get("ols run (pts)")
        r2_col = idx.get("ols R2")

        def _optf(row, col):
            if col is None:
                return None
            v = row[col].strip()
            try:
                return float(v)
            except ValueError:
                return None

        for row in r:
            try:
                t = row[ci["time"]]
                dt = datetime.fromisoformat(t)
                ct = dt.astimezone(CT)
                ctmin = ct.hour * 60 + ct.minute
                epoch = dt.timestamp()
                o = float(row[ci["open"]]); h = float(row[ci["high"]])
                lo = float(row[ci["low"]]); c = float(row[ci["close"]])
                rv = _optf(row, res_col)
                sv = _optf(row, supp_col)
                run = _optf(row, run_col)
                r2 = _optf(row, r2_col)
            except (ValueError, TypeError, IndexError):
                continue
            # tuple: (ctmin, o, h, l, c, epoch, pine_res, pine_supp, pine_run, pine_r2)
            # pine_* are None when the file lacks those exported columns (e.g. raw 5yr file).
            bars.append((ctmin, o, h, lo, c, epoch, rv, sv, run, r2))
    return bars


def pivots(highs, lows, half):
    """ta.pivothigh/low(half,half): a bar is a pivot high if its high is the strict-ish max of the
    2*half+1 window centered on it; confirmed `half` bars later. Returns per-bar (lastResLine,
    lastSuppLine) using the most recent confirmed pivot, exactly like the Pine's last-fractal vars."""
    n = len(highs)
    res_line = [None] * n
    supp_line = [None] * n
    last_hi = None
    last_lo = None
    for i in range(n):
        # a pivot centered at c = i-half is confirmable now (needs half bars on each side)
        c = i - half
        if c - half >= 0 and c + half < n and c >= 0:
            hv = highs[c]
            if all(highs[c] >= highs[j] for j in range(c - half, c + half + 1)):
                last_hi = hv
            lv = lows[c]
            if all(lows[c] <= lows[j] for j in range(c - half, c + half + 1)):
                last_lo = lv
        res_line[i] = last_hi
        supp_line[i] = last_lo
    return res_line, supp_line


def ols(close, i, N):
    if i < N - 1:
        return (None, None)
    yref = close[i - (N - 1)]
    sx = sy = sxx = syy = sxy = 0.0
    for k in range(N):
        x = float(k)
        y = close[i - (N - 1) + k] - yref
        sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y
    fN = float(N)
    vX = sxx - sx * sx / fN
    vY = syy - sy * sy / fN
    cXY = sxy - sx * sy / fN
    if vX > 0 and vY > 0:
        return (cXY / vX, cXY * cXY / (vX * vY))
    return (None, None)


def detect(bars, win_len=WIN_LEN, run_min=RUN_MIN, min_r2=MIN_R2, pullback=PULLBACK,
           break_tol=BREAK_TOL, sr_half=SR_HALF):
    """Run the expensive detector ONCE. Returns per-bar signal arrays (config-invariant for the
    trail x stop_buf sweep). long_sig[i]/short_sig[i] are the triangle fires; faded_ext_*[i] is
    the extreme to reference for the initial stop on that entry."""
    high = [b[2] for b in bars]; low = [b[3] for b in bars]; close = [b[4] for b in bars]
    n = len(bars)
    # If the file exported Pine's exact S/R lines (strategy export), USE THEM -- my pivots() differs
    # from ta.pivothigh at some bars (verified: 07-15 23:16 mine=29749 vs Pine=29721.5, which is why
    # a short arm was missed). Fall back to computed pivots only when the columns are absent (5yr).
    have_pine_sr = any(b[6] is not None for b in bars)
    if have_pine_sr:
        res_line = [b[6] for b in bars]
        supp_line = [b[7] for b in bars]
    else:
        res_line, supp_line = pivots(high, low, sr_half)

    # Pine's exported ols run/R2 are the OLS GROUND TRUTH. Recomputing from the CSV close gives a
    # different value because the CSV drops bars the live chart included, so a plain 150-bar lookback
    # spans different real bars (07-13 03:25: mine 252 vs Pine 356). Use Pine's when present; my ols()
    # only supplies the SIGN (up/down), which is direction-correct regardless of magnitude.
    have_pine_run = any(b[8] is not None for b in bars)
    pine_run = [b[8] for b in bars]
    pine_r2 = [b[9] for b in bars]

    epoch = [b[5] for b in bars]

    long_sig = [False] * n
    short_sig = [False] * n
    fext_long = [None] * n
    fext_short = [None] * n

    sA = lA = False
    sE = lE = None
    lock_low = lock_high = None
    bars_since_gap = 0    # contiguous bars since the last >60min session break
    for i in range(n):
        # SESSION-GAP handling: a >60min gap (weekend/holiday) means the winLen-bar OLS window would
        # straddle the break and fit garbage (the bogus 05 Jul short). Count clean bars; the OLS only
        # qualifies with winLen contiguous bars, and the gap CLEARS the arm/lock state.
        gap_now = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        bars_since_gap = 1 if gap_now else bars_since_gap + 1
        window_clean = bars_since_gap >= win_len
        if gap_now:
            sA = lA = False
            sE = lE = None
            lock_low = lock_high = None

        s, r = ols(close, i, win_len)
        if have_pine_run:
            run = pine_run[i]
            r = pine_r2[i] if pine_r2[i] is not None else r
        else:
            run = abs(s) * (win_len - 1) if s is not None else None
        sign = 0 if s is None else (1 if s > 0 else -1)
        q = window_clean and s is not None and run is not None and r is not None \
            and r >= min_r2 and run >= run_min
        has_up, has_down = q and sign > 0, q and sign < 0
        rl, sl = res_line[i], supp_line[i]
        t_res = rl is not None and high[i] >= rl and close[i] <= rl + break_tol
        t_sup = sl is not None and low[i] <= sl and close[i] >= sl - break_tol
        if lock_high is not None and high[i] > lock_high:
            lock_high = None
        if lock_low is not None and low[i] < lock_low:
            lock_low = None
        if not sA:
            if has_up and t_res and lock_high is None:
                sA, sE = True, high[i]
        else:
            sE = max(sE, high[i])
            if close[i] <= sE - pullback:
                short_sig[i] = True; fext_short[i] = sE
                lock_high, sA, sE = sE, False, None
        if not lA:
            if has_down and t_sup and lock_low is None:
                lA, lE = True, low[i]
        else:
            lE = min(lE, low[i])
            if close[i] >= lE + pullback:
                long_sig[i] = True; fext_long[i] = lE
                lock_low, lA, lE = lE, False, None
    return long_sig, short_sig, fext_long, fext_short


def trade_loop(bars, sig, block_ny=BLOCK_NY, block_ln=BLOCK_LN, mult=2.0,
               enable_trail=False, trail=TRAIL, enable_init=False, stop_buf=STOP_BUF, **_ignored):
    """Mirrors the toggled .pine. DEFAULT = SESSION-HOLD (enable_trail=enable_init=False), which
    matches the validated TV export: enter on triangle, exit ONLY on session flatten / opposite.
    Optional stops (to validate the toggles):
      * enable_init: hard stop beyond the faded extreme (long: fext-stop_buf, short: fext+stop_buf)
      * enable_trail: trailing stop `trail` pts off the best price since entry
    When both are on, the stop each bar is the TIGHTEST enabled level (max for long / min for short),
    checked intrabar against low/high -- same construction as the .pine.

    trades = (dir, entry, exit, pts, usd); usd = pts*mult (MNQ $2/pt) -> compares to TV 'Net PnL USD'."""
    long_sig, short_sig, fext_long, fext_short = sig
    ctmin = [b[0] for b in bars]; high = [b[2] for b in bars]
    low = [b[3] for b in bars]; close = [b[4] for b in bars]; epoch = [b[5] for b in bars]
    n = len(bars)

    pos = 0
    entry_px = init_stop = best = None
    trades = []

    def _close(direction, px):
        pts = (px - entry_px) if direction > 0 else (entry_px - px)
        trades.append((direction, entry_px, px, pts, pts * mult))

    for i in range(n):
        cm = ctmin[i]
        gap_edge = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        session_flat = (900 <= cm < 960) or (block_ny and 510 <= cm < 540) \
            or (block_ln and 120 <= cm < 150) or gap_edge
        closed_this_bar = False
        reversed_this_bar = False

        # OPPOSITE signal = close AND REVERSE (verified vs TV trade-list: every 'opposite' exit is
        # immediately followed by a same-bar entry the other way). Close the current trade at close,
        # then open the opposite at the same close on this bar.
        if pos > 0 and short_sig[i] and not session_flat:
            _close(1, close[i])
            pos = -1; entry_px = close[i]; best = low[i]
            init_stop = (fext_short[i] + stop_buf) if fext_short[i] is not None else None
            reversed_this_bar = True
        elif pos < 0 and long_sig[i] and not session_flat:
            _close(-1, close[i])
            pos = 1; entry_px = close[i]; best = high[i]
            init_stop = (fext_long[i] - stop_buf) if fext_long[i] is not None else None
            reversed_this_bar = True

        if not reversed_this_bar and pos > 0 and (enable_trail or enable_init):
            best = max(best, high[i])
            sl = None
            if enable_init:
                sl = init_stop
            if enable_trail:
                t = best - trail
                sl = t if sl is None else max(sl, t)
            if sl is not None and low[i] <= sl:
                _close(1, sl); pos = 0; entry_px = init_stop = best = None; closed_this_bar = True
        elif not reversed_this_bar and pos < 0 and (enable_trail or enable_init):
            best = min(best, low[i])
            sl = None
            if enable_init:
                sl = init_stop
            if enable_trail:
                t = best + trail
                sl = t if sl is None else min(sl, t)
            if sl is not None and high[i] >= sl:
                _close(-1, sl); pos = 0; entry_px = init_stop = best = None; closed_this_bar = True

        if session_flat and pos != 0:
            _close(pos, close[i]); pos = 0; entry_px = init_stop = best = None; closed_this_bar = True

        # process_orders_on_close: a bar that closed a position enters the NEXT bar flat, so no
        # same-bar re-entry. Deferring the entry to the following bar is what aligns the sequence
        # with Pine and kills the exit-timing cascade.
        if pos == 0 and not session_flat and not closed_this_bar and not reversed_this_bar:
            if long_sig[i] and not short_sig[i]:
                pos = 1; entry_px = close[i]; best = high[i]
                init_stop = (fext_long[i] - stop_buf) if fext_long[i] is not None else None
            elif short_sig[i] and not long_sig[i]:
                pos = -1; entry_px = close[i]; best = low[i]
                init_stop = (fext_short[i] + stop_buf) if fext_short[i] is not None else None

    # close any position still open at the end of data (TV's "Open" exit on the last bar)
    if pos != 0:
        _close(pos, close[-1])
    return trades


def backtest(bars, win_len=WIN_LEN, run_min=RUN_MIN, min_r2=MIN_R2, pullback=PULLBACK,
             break_tol=BREAK_TOL, sr_half=SR_HALF, trail=TRAIL, stop_buf=STOP_BUF,
             block_ny=BLOCK_NY, block_ln=BLOCK_LN):
    sig = detect(bars, win_len, run_min, min_r2, pullback, break_tol, sr_half)
    return trade_loop(bars, sig, trail, stop_buf, block_ny, block_ln)


def stats(trades):
    """trades are (dir, entry, exit, pts, usd). Reports net in POINTS and USD ($2/pt) so it can be
    compared against TV's 'Net PnL USD' directly."""
    if not trades:
        return dict(n=0, net=0.0, usd=0.0, wins=0, losses=0, wr=0.0, pf=0.0, avg=0.0)
    net = sum(t[3] for t in trades)          # points
    usd = sum(t[4] for t in trades)          # dollars
    wins = [t[3] for t in trades if t[3] > 0]
    losses = [t[3] for t in trades if t[3] <= 0]
    gp = sum(wins); gl = -sum(losses)
    pf = (gp / gl) if gl > 0 else float("inf")
    return dict(n=len(trades), net=net, usd=usd, wins=len(wins), losses=len(losses),
                wr=100.0 * len(wins) / len(trades), pf=pf, avg=net / len(trades))


def fmt(label, s):
    pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    print(f"  {label:<10} trades={s['n']:>5}  net={s['net']:>9.1f}pt  ${s['usd']:>9.1f}  "
          f"win%={s['wr']:>5.1f}  PF={pf:>5}  avg={s['avg']:>6.1f}pt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()

    print("loading data (normalizing to Chicago)...")
    b5 = load(FIVE_YR)
    boos = load(OOS)
    print(f"  5yr bars: {len(b5)}   OOS bars: {len(boos)}")

    if not a.sweep:
        print(f"\nDEFAULTS win={WIN_LEN} runMin={RUN_MIN} R2={MIN_R2} pull={PULLBACK} "
              f"trail={TRAIL} stopBuf={STOP_BUF} NYblk={BLOCK_NY} LNblk={BLOCK_LN}")
        fmt("5yr", stats(backtest(b5)))
        fmt("OOS", stats(backtest(boos)))
        return

    print("\ndetecting signals once per file (this is the slow step)...")
    sig5 = detect(b5)
    sigo = detect(boos)
    print("SWEEP trailPts x stopBufPts  (5yr net / PF  |  OOS net / PF)")
    print(f"  {'trail':>5} {'sBuf':>5} | {'5yr net':>10} {'5yrPF':>6} {'5yrN':>5} | "
          f"{'OOS net':>9} {'OOSPF':>6} {'OOSN':>5}")
    for trail in (40, 60, 80, 100, 130):
        for sbuf in (5, 10, 20):
            s5 = stats(trade_loop(b5, sig5, trail=trail, stop_buf=sbuf))
            so = stats(trade_loop(boos, sigo, trail=trail, stop_buf=sbuf))
            pf5 = "inf" if s5["pf"] == float("inf") else f"{s5['pf']:.2f}"
            pfo = "inf" if so["pf"] == float("inf") else f"{so['pf']:.2f}"
            print(f"  {trail:>5} {sbuf:>5} | {s5['net']:>10.0f} {pf5:>6} {s5['n']:>5} | "
                  f"{so['net']:>9.0f} {pfo:>6} {so['n']:>5}")


if __name__ == "__main__":
    main()
