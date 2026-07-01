# Offline backtest harness for slope_strategy.pine

A dependency-free Python port of `slope_strategy.pine` that replays 1-minute
OHLC bar-by-bar, reproducing the Pine state machine. Used to sweep parameters
and validate entry filters **before** touching the live strategy — Pine can't
run locally.

## Files
- `backtest.py` — the port. `load()`, `run(bars, params)`, `stats(trades)`.
- `sweep.py`    — broad grid sweep over the high-leverage knobs; writes `results.txt`.
- `refine.py`   — in-sample / out-of-sample (60/40) refinement around a chosen config.

## Data
Reads `~/Downloads/data.csv` (exported from TradingView: time, OHLC, ...).
Timestamps may be in any timezone offset — the loader normalizes to
America/Chicago (matching Pine's `hour(time,"America/Chicago")`) for the
session-window logic. Use the full multi-week export (~24k bars) for anything
you'll act on; a single day overfits.

## Run
Use the system Python (the anaconda one has a broken pandas; this port only
needs stdlib):

    /usr/bin/python3 backtest.py          # prints baseline stats + exit-reason mix
    /usr/bin/python3 sweep.py             # grid sweep -> results.txt
    /usr/bin/python3 refine.py            # IS/OOS around CENTER (edit CENTER first)

Current tuned baseline (defaults matching the Pine file): ~639 trades, 68.5%
win, +6609 pts on the Jun 7–Jul 1 dataset. PnL is in POINTS — multiply by the
contract $/pt (MNQ = $2) for dollars.

## Fidelity notes (read before trusting a result)
- Bar-close model (matches `calc_on_every_tick=false`). One row = one bar.
- Same-bar SL is checked BEFORE TP (conservative). Fills: SL pins at the SL
  price, TP at the TP price, TRAIL/TEXP/THRD/BLK/EOD at bar close.
- No commission / slippage. Directionally reliable for RANKING params, not
  exact-dollar.
- Session windows stay anchored to America/Chicago regardless of the CSV's
  stamp timezone (same as the Pine strategy).

## Workflow for any new entry filter
1. Add the filter to `run()` behind a param flag (default off).
2. Compare with/without via `refine.py` on the FULL dataset, IS vs OOS.
3. Also check the win/loss split of the trades the filter REMOVES — if it
   deletes net profit, don't ship it. (Several plausible filters have been
   rejected this way; the strategy is a mean-reversion fade and momentum-
   respecting filters tend to cut winners.)
