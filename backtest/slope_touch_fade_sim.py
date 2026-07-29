#!/usr/bin/env python3
"""
Offline simulation of slope_touch_fade.pine ("Nara") — the pullback-confirmed
trend-END fade detector. Mirrors the Pine state machine exactly so we can trace
any date without loading TradingView.

USAGE
  python3 slope_touch_fade_sim.py <ohlc_json> [--from HH:MM] [--to HH:MM] [--trace]

  <ohlc_json>  a saved get_ohlc_data result file (the JSON with a "bars" array).
  --from/--to  restrict the bar-by-bar trace to a London-time window (events are
               always printed for the whole file).
  --trace      also print the per-bar armed-side path (low/close/extreme/pullback).

The OLS math, the arm/track/fire/lock state machine, and the defaults are kept in
lockstep with the .pine. If you change a default in the indicator, change it here.
"""
import json
import sys
import argparse

# --- defaults: keep in sync with slope_touch_fade.pine inputs ---
WIN_LEN = 150       # winLen  (fixed OLS window)
RUN_MIN = 100.0     # runMinPts
MIN_R2 = 0.75       # minR2
PULLBACK_PTS = 70.0 # pullbackPts
BREAK_TOL = 5.0     # breakTol: touch void if close is beyond the line by more than this


def ols(close, i, N):
    """Numerically-stable OLS over close[i-N+1 .. i]. Returns (slope, r2) or (None, None).
    Centers y on the oldest sample, exactly like the Pine olsScan()."""
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


def load_bars(path):
    with open(path) as fh:
        data = json.load(fh)
    bars = data["bars"]
    return {
        "close": [b["close"] for b in bars],
        "high": [b["high"] for b in bars],
        "low": [b["low"] for b in bars],
        "supp": [b.get("support (pivot low)") for b in bars],
        "res": [b.get("resistance (pivot high)") for b in bars],
        "tm": [b["time"][11:16] for b in bars],
    }


def simulate(d, win_len=WIN_LEN, run_min=RUN_MIN, min_r2=MIN_R2, pullback=PULLBACK_PTS,
             break_tol=BREAK_TOL):
    """Run the exact arm/track/fire/lock machine. Returns a list of event dicts."""
    close, high, low = d["close"], d["high"], d["low"]
    supp, res, tm = d["supp"], d["res"], d["tm"]
    n = len(close)
    slopes = [ols(close, i, win_len)[0] for i in range(n)]
    r2s = [ols(close, i, win_len)[1] for i in range(n)]

    events = []
    sA = lA = False
    sE = lE = None
    lock_low = lock_high = None
    for i in range(n):
        s, r = slopes[i], r2s[i]
        if s is None:
            continue
        run = abs(s) * (win_len - 1)
        q = r >= min_r2 and run >= run_min
        has_up, has_down = q and s > 0, q and s < 0
        # touch void if price closed clearly beyond the line (level already broken)
        t_res = res[i] is not None and high[i] >= res[i] and close[i] <= res[i] + break_tol
        t_sup = supp[i] is not None and low[i] <= supp[i] and close[i] >= supp[i] - break_tol

        # clear locks on a genuinely new extreme past the fired one
        if lock_high is not None and high[i] > lock_high:
            lock_high = None
        if lock_low is not None and low[i] < lock_low:
            lock_low = None

        # SHORT side (rising trend into resistance)
        if not sA:
            if has_up and t_res and lock_high is None:
                sA, sE = True, high[i]
                events.append({"t": tm[i], "kind": "SHORT-ARM", "px": high[i],
                               "slope": s, "run": run})
        else:
            sE = max(sE, high[i])
            if close[i] <= sE - pullback:
                events.append({"t": tm[i], "kind": "SHORT-FIRE", "ext": sE,
                               "close": close[i], "pb": sE - close[i]})
                lock_high, sA, sE = sE, False, None

        # LONG side (falling trend into support)
        if not lA:
            if has_down and t_sup and lock_low is None:
                lA, lE = True, low[i]
                events.append({"t": tm[i], "kind": "LONG-ARM", "px": low[i],
                               "slope": s, "run": run})
        else:
            lE = min(lE, low[i])
            if close[i] >= lE + pullback:
                events.append({"t": tm[i], "kind": "LONG-FIRE", "ext": lE,
                               "close": close[i], "pb": close[i] - lE})
                lock_low, lA, lE = lE, False, None

    return events, slopes, r2s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ohlc_json")
    ap.add_argument("--from", dest="t0", default=None)
    ap.add_argument("--to", dest="t1", default=None)
    ap.add_argument("--trace", action="store_true")
    a = ap.parse_args()

    d = load_bars(a.ohlc_json)
    events, slopes, _ = simulate(d)

    print(f"defaults: winLen={WIN_LEN} runMin={RUN_MIN} minR2={MIN_R2} pullback={PULLBACK_PTS}")
    print(f"bars: {len(d['close'])}   events: {len(events)}")
    for e in events:
        if e["kind"].endswith("ARM"):
            print(f"  {e['t']} {e['kind']:<10} px={e['px']} slope={e['slope']:.2f} run={e['run']:.0f}")
        else:
            print(f"  {e['t']} {e['kind']:<10} ext={e['ext']:.1f} close={e['close']} pb={e['pb']:.1f}")

    if a.trace and a.t0 and a.t1:
        tm, low, close = d["tm"], d["low"], d["close"]
        # find the most recent long-arm before/within the window to anchor the extreme
        arm_i = None
        for i, t in enumerate(tm):
            if any(ev["t"] == t and ev["kind"] == "LONG-ARM" for ev in events):
                arm_i = i
        print(f"\ntrace {a.t0} -> {a.t1} (extreme anchored at last long-arm):")
        ext = None
        for i, t in enumerate(tm):
            if arm_i is not None and i >= arm_i:
                ext = low[i] if ext is None else min(ext, low[i])
            if a.t0 <= t <= a.t1 and ext is not None:
                print(f"  {t} low={low[i]} close={close[i]} extLow={ext:.1f} pbOffExt={close[i]-ext:.1f}")


if __name__ == "__main__":
    main()
