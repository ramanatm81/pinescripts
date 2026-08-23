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
import hashlib
import threading

import pyarrow.parquet as pq
import pyarrow.compute as pc
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

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


# ------- simulation: strategy registry + async job engine -------
# Each strategy declares (a) a param schema the UI form is built from and (b) a builder that turns
# a validated cfg into (frames, trades, meta). Adding a strategy = one registry entry; the frontend
# form is fully data-driven from the schema, no frontend change needed for new params.
#
# Param schema field: {name, label, type: 'int'|'float'|'bool', default, min?, max?, step?, group}

def _wdf_schema():
    import wdf_sim  # noqa: F401 (import here so backend imports even if numba missing)
    return dict(
        strategy="window_displacement_fade",
        label="Window Displacement Fade",
        params=[
            dict(name="win_len", label="window (bars)", type="int", default=30, min=2, group="Signal"),
            dict(name="thr", label="displacement thr", type="float", default=130, min=1, group="Signal"),
            dict(name="prev_block", label="prev filter on", type="bool", default=True, group="Signal"),
            dict(name="prev_win", label="prev window (bars)", type="int", default=30, min=1, group="Signal"),
            dict(name="prev_thr", label="prev reverse >(pt)", type="float", default=50, min=0, group="Signal"),
            dict(name="tp", label="take-profit (pt)", type="float", default=70, min=1, group="Exit"),
            dict(name="sl", label="stop-loss (pt)", type="float", default=50, min=1, group="Exit"),
            dict(name="block_after_tp", label="block after TP", type="bool", default=False, group="Exit"),
            dict(name="min_r2", label="min R² for block", type="float", default=0.8, min=0, max=1, step=0.05, group="Exit"),
            dict(name="block_ny", label="block NY", type="bool", default=True, group="Session"),
            dict(name="block_ln", label="block LN", type="bool", default=True, group="Session"),
        ],
    )


def _wdf_build(dataset, cfg, start=None, end=None):
    import wdf_sim
    return wdf_sim.build_run(dataset, cfg, start=start, end=end)


def _orb_schema():
    import orb_sim  # noqa: F401
    return dict(
        strategy="opening_range_breakout",
        label="Opening-Range Breakout (Sapporo)",
        params=[
            dict(name="or_minutes", label="OR window (min)", type="int", default=30, min=1, max=120, group="Range"),
            dict(name="break_end_min", label="break window end (min)", type="int", default=120, min=1, max=390, group="Range"),
            dict(name="break_buf", label="break buffer (pt)", type="float", default=3, min=0, step=0.5, group="Range"),
            dict(name="or_min_pts", label="min OR width (pt, 0=off)", type="float", default=0, min=0, step=5, group="Range"),
            dict(name="exit_mode", label="exit (0trail 1fix 2ORmult 3EOD)", type="int", default=3, min=0, max=3, group="Exit"),
            dict(name="trail_pts", label="trail dist (pt)", type="float", default=150, min=1, step=5, group="Exit"),
            dict(name="tp_pts", label="fixed TP (pt)", type="float", default=120, min=1, step=5, group="Exit"),
            dict(name="sl_pts", label="fixed SL (pt)", type="float", default=80, min=1, step=5, group="Exit"),
            dict(name="tp_mult", label="ORmult TP xOR", type="float", default=1, min=0.1, step=0.1, group="Exit"),
            dict(name="sl_mult", label="ORmult SL xOR", type="float", default=1, min=0.1, step=0.1, group="Exit"),
            dict(name="use_cat", label="cat stop on", type="bool", default=True, group="Cat stop"),
            dict(name="cat_mult", label="cat dist xATR", type="float", default=1.5, min=0.25, step=0.25, group="Cat stop"),
            dict(name="atr_days", label="ATR lookback (days)", type="int", default=14, min=1, max=60, group="Cat stop"),
            dict(name="use_slope", label="slope router on", type="bool", default=False, group="Router"),
            dict(name="slope_len", label="slope window (bars)", type="int", default=15, min=2, max=120, group="Router"),
            dict(name="slope_min", label="min slope (pt/bar)", type="float", default=1, min=0, step=0.25, group="Router"),
            dict(name="enable_long", label="take longs", type="bool", default=True, group="Side"),
            dict(name="enable_short", label="take shorts", type="bool", default=True, group="Side"),
        ],
    )


def _orb_build(dataset, cfg, start=None, end=None):
    import orb_sim
    return orb_sim.build_run(dataset, cfg, start=start, end=end)


def _orb_verify(dataset, cfg):
    import orb_sim
    return orb_sim.verify(dataset, cfg)


def _wdf_verify(dataset, cfg):
    import wdf_sim
    return wdf_sim.verify(dataset, cfg)


def _od_schema():
    import open_drive_sim  # noqa: F401
    return dict(
        strategy="open_drive",
        label="Open-Drive Momentum (Otaru)",
        params=[
            dict(name="trig_pts", label="drive trigger (pt from open)", type="float", default=120, min=5, step=5, group="Trigger"),
            dict(name="settle_min", label="delay arming (min, 0=at open)", type="int", default=0, min=0, max=180, group="Trigger"),
            dict(name="entry_end_min", label="no entry after (min)", type="int", default=330, min=10, max=390, group="Trigger"),
            dict(name="use_atr_stop", label="ATR stop on", type="bool", default=True, group="Exit"),
            dict(name="sl_mult", label="stop dist xATR (avoid <=0.5)", type="float", default=1.0, min=0.25, step=0.25, group="Exit"),
            dict(name="atr_days", label="ATR lookback (days)", type="int", default=3, min=1, max=60, group="Exit"),
            dict(name="use_slope_gate", label="pre-open slope gate on", type="bool", default=False, group="Gate"),
            dict(name="slope_min", label="min |pre-open slope| (pt/bar)", type="float", default=0.75, min=0, step=0.05, group="Gate"),
            dict(name="enable_long", label="take longs", type="bool", default=True, group="Side"),
            dict(name="enable_short", label="take shorts", type="bool", default=True, group="Side"),
        ],
    )


def _od_build(dataset, cfg, start=None, end=None):
    import open_drive_sim
    return open_drive_sim.build_run(dataset, cfg, start=start, end=end)


def _od_verify(dataset, cfg):
    import open_drive_sim
    return open_drive_sim.verify(dataset, cfg)


STRATEGY_REGISTRY = {
    "window_displacement_fade": dict(schema=_wdf_schema, build=_wdf_build, verify=_wdf_verify, tag_prefix="wdf"),
    "opening_range_breakout": dict(schema=_orb_schema, build=_orb_build, verify=_orb_verify, tag_prefix="orb"),
    "open_drive": dict(schema=_od_schema, build=_od_build, verify=_od_verify, tag_prefix="od"),
}


def _coerce(schema, params):
    """Validate/coerce incoming params against the schema; fill defaults; clamp to min/max."""
    out = {}
    for f in schema["params"]:
        v = params.get(f["name"], f["default"])
        if f["type"] == "int":
            v = int(v)
        elif f["type"] == "float":
            v = float(v)
        elif f["type"] == "bool":
            v = bool(v)
        if "min" in f and isinstance(v, (int, float)) and v < f["min"]:
            v = f["min"]
        if "max" in f and isinstance(v, (int, float)) and v > f["max"]:
            v = f["max"]
        out[f["name"]] = v
    return out


def _tag_for(strategy, dataset, cfg, start=None, end=None):
    prefix = STRATEGY_REGISTRY[strategy]["tag_prefix"]
    payload = json.dumps(dict(cfg=cfg, start=start, end=end), sort_keys=True)
    h = hashlib.sha1(payload.encode()).hexdigest()[:8]
    rng = ""
    if start or end:
        rng = "_" + (start or "").replace("-", "") + "-" + (end or "").replace("-", "")
    return f"{prefix}_{dataset}{rng}_{h}"


_JOBS = {}            # job_id -> {state, tag?, error?, strategy, dataset, cfg}
_JOBS_LOCK = threading.Lock()
_SIM_LOCK = threading.Lock()   # one heavy generate at a time (single local user)
_VERIFIED = set()     # (strategy, dataset) pairs whose oracle-verify already passed this session


def _run_job(job_id):
    job = _JOBS[job_id]
    strategy, dataset, cfg = job["strategy"], job["dataset"], job["cfg"]
    start, end = job["start"], job["end"]
    reg = STRATEGY_REGISTRY[strategy]
    tag = _tag_for(strategy, dataset, cfg, start, end)
    path = _run_path(tag)
    try:
        if os.path.exists(path):
            with _JOBS_LOCK:
                job.update(state="done", tag=tag, cached=True)
            return
        with _JOBS_LOCK:
            job.update(state="running")
        with _SIM_LOCK:
            import frames_export as fx
            # oracle gate: first time we generate for a strategy, assert sim==port over the FULL
            # dataset (the range slicing is separately proven identical to a full-series restriction).
            if strategy not in _VERIFIED and reg.get("verify"):
                ok, msg = reg["verify"]("oos", cfg)
                print(f"[simulate] VERIFY {strategy}: {'OK' if ok else 'FAIL'} -- {msg}")
                if not ok:
                    raise RuntimeError(f"oracle verify failed: {msg}")
                _VERIFIED.add(strategy)
            frames, trades, meta = reg["build"](dataset, cfg, start=start, end=end)
            meta["tag"] = tag
            fx.write_parquet(frames, trades, meta, path)
        _CACHE.pop(tag, None)   # ensure /runs + /run pick up the fresh file
        with _JOBS_LOCK:
            job.update(state="done", tag=tag, cached=False)
    except Exception as ex:  # surface to the poller instead of dying silently
        with _JOBS_LOCK:
            job.update(state="error", error=str(ex))


class SimulateBody(BaseModel):
    strategy: str
    dataset: str = "5yr"
    params: dict = {}
    start: str | None = None   # CT-date ISO prefix, inclusive (e.g. "2024-01"); None = dataset start
    end: str | None = None     # inclusive (e.g. "2024-03"); None = dataset end


# ------- endpoints -------
@app.get("/strategies")
def strategies():
    """List registered strategies (for the New Run form's strategy dropdown)."""
    return [dict(strategy=k, label=v["schema"]()["label"]) for k, v in STRATEGY_REGISTRY.items()]


@app.get("/params/{strategy}")
def params(strategy: str):
    if strategy not in STRATEGY_REGISTRY:
        raise HTTPException(404, f"unknown strategy '{strategy}'")
    return STRATEGY_REGISTRY[strategy]["schema"]()


@app.post("/simulate")
def simulate(body: SimulateBody):
    if body.strategy not in STRATEGY_REGISTRY:
        raise HTTPException(404, f"unknown strategy '{body.strategy}'")
    if body.dataset not in ("5yr", "oos"):
        raise HTTPException(400, "dataset must be '5yr' or 'oos'")
    schema = STRATEGY_REGISTRY[body.strategy]["schema"]()
    cfg = _coerce(schema, body.params)
    start = body.start or None
    end = body.end or None
    tag = _tag_for(body.strategy, body.dataset, cfg, start, end)
    # if already built, report done immediately (no job needed)
    if os.path.exists(_run_path(tag)):
        return dict(job_id=None, tag=tag, state="done", cached=True)
    job_id = hashlib.sha1(f"{tag}".encode()).hexdigest()[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = dict(state="queued", strategy=body.strategy, dataset=body.dataset,
                             cfg=cfg, start=start, end=end, tag=None, error=None)
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return dict(job_id=job_id, tag=tag, state="queued")


@app.get("/job/{job_id}")
def job_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(404, f"no job '{job_id}'")
        return {k: job[k] for k in ("state", "tag", "error") if k in job}


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


# Static assets (JS/CSS/vendor) are served with no-cache so an edit to app.js shows on a plain
# reload -- the frontend is developed live and browser caching a stale app.js was a recurring trap.
_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/")
def index():
    fp = os.path.join(FRONTEND, "index.html")
    if os.path.exists(fp):
        return FileResponse(fp, headers=_NO_CACHE)
    return JSONResponse(dict(
        service="replay-backtest-backend",
        runs_endpoint="/runs",
        note="frontend/index.html not built yet (next milestone)",
    ))


@app.get("/static/{path:path}")
def static_asset(path: str):
    # serve any file under FRONTEND, no-cache, with a path-traversal guard
    full = os.path.normpath(os.path.join(FRONTEND, path))
    if not full.startswith(os.path.abspath(FRONTEND) + os.sep) or not os.path.isfile(full):
        raise HTTPException(404, f"no static asset '{path}'")
    return FileResponse(full, headers=_NO_CACHE)
