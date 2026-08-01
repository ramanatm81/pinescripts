# Replay Backtest UI — Build Plan

A local tool that loads a custom OHLCV CSV, runs a Pine-ported strategy over it, and lets you
**replay** the backtest bar-by-bar on a chart (see S/R, arm dots, entries/exits, live P&L, equity),
plus scrub to any date, jump between trades, and read the trade table. Fills the gap TradingView
leaves: TV can't backtest a strategy on your own uploaded 5-year CSV.

## Why this, not a switch to Backtrader/NinjaTrader
We already have a **bar-exact validated port** (`backtest/slope_touch_fade_bt.py`) that reproduces
the TradingView Strategy Tester to the dollar (+3051 OOS, 32 trades, diff 0.0). Rewriting the
strategy in another engine (Backtrader/AFL/EasyLanguage) reintroduces the exact fidelity problem we
already solved. So the plan is: **wrap the existing port in a UI**, not adopt a new engine.

## Scope (v1)
- Load any OHLCV CSV (`time,open,high,low,close,Volume`; the 5yr file is `ohlcv/mnq_5yr.csv`).
- Run one strategy (slope-touch fade first; pluggable later) with its param inputs exposed.
- **Replay**: play/pause/step/scrub through bars; candlestick chart with overlays.
- Live panels: open position, running P&L, equity curve, trade log.
- Jump-to: next/prev trade, next/prev losing trade, go-to-date, go-to-month.
- Show WHY each entry/exit fired (arm dot, pullback, stop, session, opposite-reverse).

## Architecture (recommended)
**Backend: Python (FastAPI) reusing the existing port. Frontend: single-page web app (chart lib).**

```
CSV ──> port (detect + trade_loop) ──> precomputed per-bar frames + trade list (JSON)
                                              │
                                    FastAPI serves frames/trades
                                              │
                                    Browser: chart + replay controls
```

Why precompute the whole run once (not stream a live engine): the strategy is deterministic and the
port already runs 5yr in ~2 min. Precompute ALL per-bar state to a JSON/Arrow blob, then the UI
just *plays back* frames — instant scrub, no recompute. This is the key design decision.

### Per-bar frame (what the port must emit for each bar)
Extend the port's detect()+trade_loop to record, per bar index:
- OHLC + time
- S/R lines (resistance, support) — already computed
- arm state (long/short armed?, arm-dot fired this bar?, run size, R²)
- signal (long/short triangle this bar?)
- position (dir, entry price), active stop level (init vs trail), stop kind
- realized cumulative P&L (USD), open trade unrealized P&L
- exit event this bar (reason: stop/session/opposite-reverse) + trade P&L

### Trade list (already produced by the port)
dir, entry_time, exit_time, entry_px, exit_px, reason, pts, USD, bars_held, cum_USD.
(The Excel export `slope_fade_5yr_trades.xlsx` is exactly this shape — reuse that generator's logic.)

## Frontend
- **Chart library:** `lightweight-charts` (TradingView's OWN open-source lib, free) — candlesticks +
  line series for S/R + markers for arm dots/entries/exits. Familiar look, handles large series.
- **Controls:** play/pause, speed (1x/5x/20x/max), step ±1 bar, scrub slider (bar index / date),
  jump-to-trade dropdown, go-to-date picker.
- **Panels:** (a) trade table (click a row → chart jumps to that trade), (b) equity curve (line of
  cum_USD), (c) current-state readout (position, stop level, P&L, why-armed).
- **Overlays on chart:** S/R lines, glowing arm dots (red=long/support, green=short/resistance —
  match the .pine), entry triangles (green L / red S), exit markers, the active stop line
  (fuchsia long / orange short), a shaded band during an open trade.

## Milestones (for the build session)
1. **Port → frames exporter.** Add a `frames()` function to the port that returns the per-bar frame
   list + trade list as JSON. Verify totals still match (+3051 OOS / +2363 5yr). ~1 file.
2. **FastAPI backend.** Endpoints: `/runs` (list), `POST /run` (csv + params → run id, cached),
   `/run/{id}/frames?from=&to=`, `/run/{id}/trades`. Cache runs on disk (pickle/parquet).
3. **Static frontend.** lightweight-charts + controls + panels. Load frames, render, wire replay.
4. **Replay engine (frontend).** requestAnimationFrame loop advancing bar index at chosen speed;
   scrub updates all panels from the precomputed frame at that index.
5. **Trade navigation + why-panel.** Click trade → seek; show entry/exit reason text.
6. **Param re-run.** Change inputs → POST /run → new cached run → reload. (Sweeps later, v2.)

## v2 / later (not v1)
- Multiple strategies (pluggable): trend-follow, trend-fade, etc. — one registry of ported detectors.
- Param sweep view (grid of results, heatmap) reusing the sweep code.
- Monthly/yearly P&L breakdown tab (reuse the monthly split logic).
- Slippage/commission inputs on the equity curve.
- Compare two runs side by side.

## Key files that already exist (reuse, don't rebuild)
- `backtest/slope_touch_fade_bt.py` — the validated port (detect + trade_loop + stats). THE engine.
- `backtest/slope_touch_fade_sim.py` — lighter sim variant.
- `ohlcv/mnq_5yr.csv` — 5yr data (UTC, ~1.77M bars).
- `~/Downloads/data.csv` — OOS export WITH Pine's exported ols/S-R columns (bar-exact reference).
- The Excel generator (was `make_excel.py`, deleted) — its trade-extraction loop is the reference
  for the trade list; lift it into the frames exporter.

## Fidelity note (carry into the build)
The port is bar-exact ONLY when it reads Pine's exported `ols run`/`ols R2`/`resistance`/`support`
columns (present in an OOS strategy-export CSV, ABSENT in the raw 5yr file). On raw CSV it RECOMPUTES
those, which diverges from Pine at a small % of bars (the raw 5yr is nearly continuous so it's close
but not exact). So: replay on an EXPORTED csv = bar-exact; replay on a RAW csv = directionally
faithful. Surface this in the UI (badge: "exact" vs "recomputed").

## Open decisions for the build session
- Web (FastAPI + browser) vs desktop (PyQt/Tkinter)? → web recommended (lightweight-charts is best-
  in-class and free; easy to share/screenshot).
- Precompute-all vs stream? → precompute-all (decided above; instant scrub).
- One strategy hardcoded first, or pluggable from the start? → hardcode slope-fade for v1, refactor
  to pluggable in v2.
