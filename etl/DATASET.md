# MNQ continuous front-month — 1-minute OHLCV

Source: Databento GLBX.MDP3 `glbx-mdp3-20210624-20260623.ohlcv-1m.dbn.zst`
(parent symbology MNQ.FUT), converted via the `dbn` CLI + DuckDB.

- **Continuous front-month**: for each trading day, the outright contract with the
  highest daily volume is the front; its bars are used. Rolls automatically ~1 week
  before expiry as volume migrates to the next quarterly (U→Z→H→M cycle).
- **Spreads and back-month contracts dropped.** 21 quarterly contracts span the range.
- Rows: 1,770,244  |  Range: 2021-06-24 → 2026-06-24  |  ~23 MB zstd parquet.
- Timestamps `ts_event` are UTC (tz-aware). `symbol` shows which contract each bar is from.
- Columns: ts_event, symbol, open, high, low, close, volume (+ partition cols year, month).

## Partitioning
`year=YYYY/month=M/data_0.parquet` — DuckDB/Arrow hive layout. Date-range queries
prune to the relevant months.

## Query examples
    duckdb -c "SELECT count(*) FROM read_parquet('mnq_continuous/**/*.parquet')"
    -- a date window:
    duckdb -c "SELECT * FROM read_parquet('mnq_continuous/**/*.parquet')
               WHERE ts_event BETWEEN '2026-06-01' AND '2026-06-30' ORDER BY ts_event"
    -- prune by partition (faster):
    duckdb -c "SELECT * FROM read_parquet('mnq_continuous/year=2026/month=6/*.parquet')"

## Roll note for backtesting
This is a **volume-rolled** front-month (no price back-adjustment). There are small
price gaps at roll boundaries (the front jumps to the next contract's price level).
For strategies using absolute point moves within a session that's fine; if you ever
need a continuous *price* series across rolls, apply a back-adjustment (panama/ratio).
