# Backtest performance notes — why the old runs were slow, why numba

## Why the original port was slow (~90s per detect over 5yr)

`slope_touch_fade_bt.py`'s `detect()` computes a rolling OLS regression bar-by-bar in **pure,
interpreted Python**:

```
for i in range(n):            # n = 1,770,244 bars (5yr of 1-min MNQ)
    for k in range(N):        # N = OLS window, e.g. 150
        sx += x; sy += y; sxx += x*x; ...   # ~5 float ops
```

That is **n × N ≈ 1.77M × 150 ≈ 265 MILLION inner iterations**, each doing a handful of float ops
*through the CPython interpreter*. Interpreted float math runs ~50-100× slower than compiled code
because every operation is a boxed-object dispatch. So one `detect()` ≈ 90s, and a **sweep**
(re-running detect per parameter value) multiplied that into 10-20 minute jobs. The walk-forward,
which runs the trade loop several times over all bars, was the worst.

## Why NOT Spark / DuckDB for this

The slowness is a **stateful sequential simulation**, not a data-query problem:
- `detect()` carries arm/lock/extreme state that depends on every prior bar.
- `trade_loop()` carries position/entry/stop state bar-to-bar.

DuckDB/Spark accelerate **set-based queries and aggregations** over big tables — they cannot express
(and gain nothing from) a bar-by-bar recurrence where row i depends on row i-1. Spark would be
strictly worse: distributing a 22MB dataset adds network/serialization overhead for zero parallelism
(the loop can't be split across rows). They remain the right tool for the **data layer** (load /
slice / store runs — the replay_tool already uses parquet+pyarrow for that), just not the sim.

## Why numba

`numba.njit` JIT-compiles the Python loop to native machine code via LLVM. It KEEPS the exact
sequential logic (unlike numpy vectorization, which can't express the stateful trade loop) but runs
it at C speed. Measured on this machine: the same 265M-iteration rolling loop over 5yr =
**0.34s cached** (1.0s first call incl. compile) vs ~90s pure Python => **~250x**.

Sweeps also parallelize across the 8 cores (each parameter value is independent) for a further ~8x
when needed — but numba alone already turns 10-min jobs into seconds.

## Setup

venv: `replay_tool/.venv` (Python 3.12). Installed `numpy 2.5.1`, `numba 0.62.1`.
- numba needs a prebuilt wheel: `pip install --only-binary :all: numba` (building llvmlite from
  source fails on 3.12).
- `@njit(cache=True)` requires the function to live in a real `.py` FILE (caching has "no locator"
  for `python -c` strings — that error is not a real failure).

## Result (measured on 5yr, 1.77M bars)

| stage | pure Python | numba (all-numpy) |
|---|---|---|
| one detect() | ~42-90s | 0.28s (JIT core) |
| full 15-value OLS-N sweep | ~13 min | **8.6s** (0.58s/config) |

Fully-JIT pipeline (`fast_sim.py`: detect + trade loop, no Python-list conversion between stages)
is **bar-exact** vs the port: N=90 -> 619 trades / 8124 net, N=150 -> 587 / 5942.5, both MATCH.
KEY lesson: the first cut (`fast_detect.detect_fast`) was only 9x because `.tolist()` conversion
dominated — the JIT core was already 150x. Keep everything numpy end-to-end; convert bars->arrays
ONCE per sweep (`fast_bars`), never convert signals back to Python lists.

Files: `fast_detect.py` (JIT detect+pivots), `fast_sim.py` (fast_bars + JIT trade_loop + sim()),
`validate_fast2.py` (correctness+speed proof). Run with `replay_tool/.venv/bin/python`.

## Correctness rule

The numba detector/trade-loop MUST produce results identical to the validated pure-Python port
(same trades, same net) before use — the port stays as the reference oracle. Speed never trumps the
bar-exact validation chain.
