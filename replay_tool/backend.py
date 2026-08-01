#!/usr/bin/env python3
"""
backend.py -- Milestone 2 of the replay-backtest UI.

Serves the precomputed run_*.parquet files (from frames_export.py) to a browser UI. The parquet is
the source of truth: meta + trades live in its embedded key-value metadata; frames are the columnar
table. Nothing is recomputed here -- this layer only SLICES and SHIPS.

Endpoints
  GET /runs                          list available runs (tag, bars, stats)
  GET /run/{tag}                     meta + full trade list (from parquet kv-metadata, tiny)
  GET /run/{tag}/frames?...          windowed frames as JSON columns
        from,to    : bar-index range [from, to)         (mutually exclusive with start/end)
        start,end  : ISO/prefix date range e.g. 2023-03 (filters on the `time` column)
        step       : downsample stride (default 1); return every step-th bar for wide views
        cols       : comma list to limit columns (default all)
  GET /run/{tag}/trades              just the trade list
  GET /                              serves the static UI (frontend/, added in the next milestone)

Run:
  .venv/bin/uvicorn backend:app --reload --port 8000
"""
import os
import io
import csv
import json
import glob

import pyarrow.parquet as pq
import pyarrow.compute as pc
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(HERE, "frontend")

app = FastAPI(title="Replay Backtest Backend")

# ------- derived quarterly-contract boundaries (date-based, approximate) -------
# The 5yr run has no contract column, so we DERIVE the front-month from the date. MNQ quarterlies
# expire the 3rd Friday of Mar/Jun/Sep/Dec (months 3/6/9/12; codes H/M/U/Z). The continuous series
# rolls ~1 week before expiry by volume, so we approximate the roll as (3rd Friday - 8 days). A bar
# belongs to the FIRST quarterly whose roll date is still in the future. This is an APPROXIMATION of
# the real volume roll (labelled "approx" in the UI) -- close, not bar-exact.
from datetime import date, timedelta

_Q_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}


def _third_friday(y, m):
    d = date(y, m, 1)
    # weekday(): Mon=0..Sun=6; Friday=4. first Friday, then +14 days = third Friday.
    first_fri = 1 + ((4 - d.weekday()) % 7)
    return date(y, m, first_fri + 14)


def _roll_date(y, m):
    return _third_friday(y, m) - timedelta(days=8)


def _contract_for(d):
    """Return (symbol, expiry_month_date) for the quarterly front-month active on date `d`."""
    y = d.year
    for (yy, mm) in [(y, 3), (y, 6), (y, 9), (y, 12), (y + 1, 3)]:
        if d < _roll_date(yy, mm):
            return f"MNQ{_Q_CODE[mm]}{yy % 100:02d}", date(yy, mm, 1)
    return f"MNQH{(y + 1) % 100:02d}", date(y + 1, 3, 1)

# ------- run discovery + parquet handle cache -------
_CACHE = {}   # tag -> {"path", "pf": ParquetFile, "meta", "trades", "n"}


def _run_path(tag):
    return os.path.join(HERE, f"run_{tag}.parquet")


def _load(tag):
    """Open a run's parquet (cached). Reads kv-metadata (meta+trades) once; keeps the ParquetFile
    handle so frame reads can push row-group filters without reopening."""
    if tag in _CACHE:
        return _CACHE[tag]
    path = _run_path(tag)
    if not os.path.exists(path):
        raise HTTPException(404, f"no run '{tag}' (looked for {os.path.basename(path)})")
    pf = pq.ParquetFile(path)
    kv = pf.metadata.metadata or {}
    meta = json.loads(kv.get(b"meta", b"{}"))
    trades = json.loads(kv.get(b"trades", b"[]"))
    entry = dict(path=path, pf=pf, meta=meta, trades=trades, n=pf.metadata.num_rows)
    _CACHE[tag] = entry
    return entry


def _list_runs():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "run_*.parquet"))):
        tag = os.path.basename(p)[len("run_"):-len(".parquet")]
        try:
            e = _load(tag)
            out.append(dict(tag=tag, n_bars=e["n"], n_trades=len(e["trades"]),
                            stats=e["meta"].get("stats", {}), cfg=e["meta"].get("cfg", {})))
        except Exception as ex:  # skip a corrupt file, don't 500 the whole list
            out.append(dict(tag=tag, error=str(ex)))
    return out


# ------- endpoints -------
@app.get("/runs")
def runs():
    return _list_runs()


@app.get("/run/{tag}")
def run_meta(tag: str):
    e = _load(tag)
    return dict(tag=tag, n_bars=e["n"], meta=e["meta"], trades=e["trades"])


@app.get("/run/{tag}/trades")
def run_trades(tag: str):
    return _load(tag)["trades"]


@app.get("/run/{tag}/index")
def run_index(tag: str):
    """Navigation index for the filter UI. Reads the `time`/`i` columns once (cached) and returns:
      span    : {start, end} ISO dates covering the run
      months  : [{key:'YYYY-MM', lo_i, hi_i, start, end}]  -- for the Month filter (default)
      contracts: [{symbol, approx, lo_i, hi_i, start, end}] -- derived quarterly front-months
    lo_i/hi_i are inclusive/exclusive bar indices so the frontend can map a selection to a window
    without re-scanning."""
    e = _load(tag)
    if "index" in e:
        return e["index"]
    pf = e["pf"]
    t = pf.read(columns=["i", "time"])
    idx = t["i"].to_pylist()
    times = t["time"].to_pylist()
    n = len(idx)

    months = []           # {key, lo_i, hi_i, start, end}
    contracts = []        # {symbol, approx, lo_i, hi_i, start, end}
    cur_month = cur_sym = None
    for k in range(n):
        iso = times[k]
        ym = iso[:7]                                  # 'YYYY-MM'
        d = date(int(iso[0:4]), int(iso[5:7]), int(iso[8:10]))
        sym, _exp = _contract_for(d)
        if ym != cur_month:
            if months:
                months[-1]["hi_i"] = idx[k]
                months[-1]["end"] = times[k - 1]
            months.append(dict(key=ym, lo_i=idx[k], hi_i=None, start=iso, end=None))
            cur_month = ym
        if sym != cur_sym:
            if contracts:
                contracts[-1]["hi_i"] = idx[k]
                contracts[-1]["end"] = times[k - 1]
            contracts.append(dict(symbol=sym, approx=True, lo_i=idx[k], hi_i=None,
                                  start=iso, end=None))
            cur_sym = sym
    if months:
        months[-1]["hi_i"] = idx[-1] + 1
        months[-1]["end"] = times[-1]
    if contracts:
        contracts[-1]["hi_i"] = idx[-1] + 1
        contracts[-1]["end"] = times[-1]

    out = dict(tag=tag, n_bars=n,
               span=dict(start=times[0], end=times[-1]),
               months=months, contracts=contracts)
    e["index"] = out
    return out


@app.get("/run/{tag}/frames")
def frames(tag: str,
           from_: int = Query(None, alias="from"),
           to: int = Query(None),
           start: str = Query(None),
           end: str = Query(None),
           step: int = Query(1, ge=1),
           cols: str = Query(None)):
    """Return a windowed, optionally-downsampled slice of frames as columnar JSON:
       {"n": <rows>, "columns": ["i","time",...], "data": {col: [...]}}.
    Index window uses row-group pushdown (read_row_groups on the matching groups). Date window
    reads the `i`/`time` columns to resolve the index bounds, then reads the row groups covering
    those bars. `step` downsamples AFTER slicing so wide ranges stay small."""
    e = _load(tag)
    pf = e["pf"]
    n = e["n"]

    want = None
    if cols:
        want = [c.strip() for c in cols.split(",") if c.strip()]

    # --- resolve [lo, hi) bar-index bounds ---
    if start is not None or end is not None:
        if from_ is not None or to is not None:
            raise HTTPException(400, "use either from/to OR start/end, not both")
        # time strings are ISO and lexicographically sortable, so a prefix like "2023-03" compares
        # correctly. '~' sorts after all time chars, so cap = end+"~" makes the end inclusive of the
        # whole prefix (e.g. all of March). Use per-row-group time min/max STATS to touch only the
        # groups overlapping [start, cap]; read `time` from just those, not all 1.77M bars.
        cap = (end + "~") if end is not None else None
        md = pf.metadata
        sch = pf.schema_arrow
        tcol = [f.name for f in sch].index("time")
        cand, off = [], 0
        for g in range(md.num_row_groups):
            rows = md.row_group(g).num_rows
            st = md.row_group(g).column(tcol).statistics
            gmin, gmax = (st.min, st.max) if (st and st.has_min_max) else (None, None)
            overlaps = True
            if gmin is not None:
                if start is not None and gmax < start:
                    overlaps = False
                if cap is not None and gmin > cap:
                    overlaps = False
            if overlaps:
                cand.append((g, off, off + rows))
            off += rows
        lo, hi = n, 0
        if cand:
            sub = pf.read_row_groups([g for g, _, _ in cand], columns=["i", "time"])
            times = sub["time"].to_pylist()
            idx = sub["i"].to_pylist()
            for k, tv in enumerate(times):
                if (start is None or tv >= start) and (cap is None or tv <= cap):
                    if idx[k] < lo:
                        lo = idx[k]
                    if idx[k] + 1 > hi:
                        hi = idx[k] + 1
        if hi <= lo:
            lo, hi = 0, 0
    else:
        lo = 0 if from_ is None else max(0, from_)
        hi = n if to is None else min(n, to)
    if hi <= lo:
        return dict(n=0, columns=want or [], data={})

    # --- read only the row groups covering [lo, hi) ---
    md = pf.metadata
    rg_bounds = []
    off = 0
    for g in range(md.num_row_groups):
        rows = md.row_group(g).num_rows
        rg_bounds.append((g, off, off + rows))
        off += rows
    groups = [g for (g, s, en) in rg_bounds if en > lo and s < hi]
    tbl = pf.read_row_groups(groups, columns=want)

    # slice to the exact window within the (group-aligned) table, then downsample
    grp_start = next(s for (g, s, en) in rg_bounds if g == groups[0])
    a = lo - grp_start
    b = hi - grp_start
    tbl = tbl.slice(a, b - a)
    if step > 1:
        keep = list(range(0, tbl.num_rows, step))
        tbl = tbl.take(keep)

    data = {name: tbl.column(name).to_pylist() for name in tbl.column_names}
    return dict(n=tbl.num_rows, lo=lo, hi=hi, step=step,
                columns=tbl.column_names, data=data)


@app.get("/")
def index():
    fp = os.path.join(FRONTEND, "index.html")
    if os.path.exists(fp):
        return FileResponse(fp)
    return JSONResponse(dict(
        service="replay-backtest-backend",
        runs_endpoint="/runs",
        note="frontend/index.html not built yet (next milestone)",
    ))


# serve static frontend assets if the dir exists (added next milestone)
if os.path.isdir(FRONTEND):
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
