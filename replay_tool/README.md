# Replay Backtest UI

Load the validated slope_touch_fade backtest, replay it bar-by-bar, filter by month/date/contract,
inspect every trade (arm dot → pullback → entry → exit, MFE/MAE, running P&L). One server serves
both the data API and the web page.

---

## Start the server

```bash
cd replay_tool && ./run.sh
```

Then open **http://127.0.0.1:8000/** (the script prints the URL). `Ctrl-C` to stop.
`PORT=8080 ./run.sh` to use a different port.

There is only ONE server — `run.sh` launches `backend.py`, which serves the API *and* the frontend.
It needs the sandbox off (socket bind); run it in a normal terminal.

First-time setup (if `.venv` is missing — it's gitignored):
```bash
/Users/maheshk81/.local/bin/python3.12 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]" pyarrow numpy numba
```

---

## Runs (what the "Run" dropdown shows)

A **run** = one saved backtest = one `run_<tag>.parquet` file. The dropdown lists every
`run_*.parquet` in this folder (smallest first, so it opens instantly on the small OOS run — switch
to a 5yr run in the dropdown). Parquets are gitignored (regenerable); create them with the exporter.

Current runs (regenerate any time):

| tag | config |
|-----|--------|
| `oos` | OOS month, session-hold (bar-exact) |
| `mnq_5yr` | 5yr, session-hold |
| `5yr_initstop` | 5yr, + initial stop (buf 10) |
| `5yr_keephours` | 5yr, init stop + keep London hours 8,9,15,16,18 |

---

## Strategies (the "+ New Run" form)

The UI generates runs itself: **+ New Run** → pick a strategy → the parameter form is built
automatically from that strategy's schema → pick a dataset and optional date range → Generate.
No exporter needed for these.

| strategy | label | engine | oracle |
|----------|-------|--------|--------|
| `window_displacement_fade` | Window Displacement Fade | `wdf_sim.py` | `backtest/window_displacement_fade_bt.py` |
| `opening_range_breakout` | Opening-Range Breakout (Sapporo) | `orb_sim.py` | `backtest/orb_bt.py` |
| `open_drive` | Open-Drive Momentum (Otaru) | `open_drive_sim.py` | `backtest/open_drive_bt.py` |

**Oracle gate:** the first time a strategy generates in a session, the backend runs its `verify()`
and refuses to write the run unless the numba sim matches the pure-Python port trade-for-trade.
That gate is the whole point — speed never overrides the port.

Verify by hand:
```bash
cd replay_tool
.venv/bin/python open_drive_sim.py --dataset 5yr --verify   # exact match on 934 trades
```

### Adding a strategy
One registry entry in `backend.py` (`schema` / `build` / `verify` / `tag_prefix`) plus a
`<name>_sim.py` exposing `build_run(dataset, cfg, start, end)` and `verify(dataset, cfg)`.
The frontend form is data-driven from the schema, so no frontend change is needed for new params.
A new *frame column* (like open-drive's `anchor`) does need three edits: the sim emits it,
`frames_export.write_parquet` lists it in BOTH `cols` and the `pa.schema`, and `app.js` adds it to
the `cols` string in `fetchWindow`. Miss the `pa.schema` one and the column is silently dropped.

### Open-Drive chart reading
`res`/`supp` carry the two drive-trigger rails (RTH open ± trigger), `anchor` is the RTH open
itself, and `stop_level` is the ATR stop once in a position. Entries are resting-stop fills, so the
entry marker sits at the rail (or at the bar open when the bar gapped through it).

---

## Create / run a DIFFERENT run for the UI

Run the exporter — it writes `run_<tag>.parquet`, and the UI picks it up automatically (refresh the
Run dropdown / reload the page). Use the venv python:

```bash
cd replay_tool
.venv/bin/python frames_export.py [flags] --out run_<tag>.parquet
```

### Flags (all optional; defaults = 5yr session-hold, freeze-at-dot, winLen from the port)
| flag | effect |
|------|--------|
| `--oos` | use the OOS Downloads/data.csv instead of the 5yr file (bar-exact) |
| `--file <csv>` | run any other OHLCV csv |
| `--stop-buf N` | enable the INITIAL stop, buffer N pts (e.g. `--stop-buf 10`) |
| `--trail N` | enable the TRAILING stop at N pts |
| `--no-ny` | disable the NY-open session block |
| `--no-ln` | disable the London-open session block |
| `--keep-hours 8,9,15,16` | only take entries in these LONDON hours (others blocked) |
| `--out <path>` | output file (default `run_<tag>.parquet`; extension picks format) |
| `--json` | also write a .json for inspection |

Note: the detector params (winLen, runMin, pullback, etc.) come from the port constants in
`../backtest/slope_touch_fade_bt.py` — edit those to sweep detector settings, or use the fast
sweep engine (`../backtest/fast_sim.py`) for that. The exporter flags cover the trade-side config.

### Examples
```bash
# session-hold 5yr (the default)
.venv/bin/python frames_export.py --out run_mnq_5yr.parquet

# 5yr with an initial stop
.venv/bin/python frames_export.py --stop-buf 10 --out run_5yr_initstop.parquet

# 5yr, init stop + keep only the productive London hours
.venv/bin/python frames_export.py --stop-buf 10 --keep-hours 8,9,15,16,18 --out run_5yr_keephours.parquet

# the bar-exact OOS month
.venv/bin/python frames_export.py --oos --out run_oos.parquet
```

The 5yr export takes ~90s (1.77M bars); OOS is a few seconds. Each run self-verifies against the
port (prints `VERIFY: OK`) unless `--keep-hours` is set (that diverges from the port by design, so
it prints `VERIFY: SKIPPED`).

After it writes, just **reload the browser** and pick the new tag in the Run dropdown.

---

## Gotchas

- **Server crashes on re-export?** Exporting over a parquet the server has open can kill uvicorn —
  restart `./run.sh` if the page stops loading.
- **Changes not showing?** The browser caches `app.js`; hard-reload (Cmd-Shift-R).
- **Times are London (BST-aware)** to match TradingView, though the data is stored Chicago-time.
