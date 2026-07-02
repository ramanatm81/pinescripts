# ETL — market data → analytics-ready Parquet

Scripts that convert raw vendor data into partitioned Parquet for backtesting.

## Files
- `dbn_to_parquet.py` — Python (DuckDB API) converter: Databento DBN(.zst)
  ohlcv-1m → MNQ **continuous front-month** partitioned Parquet.
- `dbn_to_parquet.sh` — the exact CLI pipeline (dbn CLI + DuckDB CLI), no Python.
- `DATASET.md` — documentation of the produced `mnq_continuous/` dataset
  (schema, roll logic, query examples, caveats).

## Prerequisites
- **`dbn` Rust CLI** — decode Databento files. `cargo install dbn-cli`
  (installs to `~/.cargo/bin/dbn`). Alternatively `pip install databento`.
- **DuckDB** — either the CLI (`brew install duckdb`) for the `.sh` script, or
  the Python package (`pip install duckdb`) for the `.py` script.

## Run
```bash
# shell (used to build the current dataset):
./etl/dbn_to_parquet.sh ohlcv/glbx-mdp3-20210624-20260623.ohlcv-1m.dbn.zst ohlcv/mnq_continuous

# or python:
python etl/dbn_to_parquet.py ohlcv/glbx-mdp3-20210624-20260623.ohlcv-1m.dbn.zst ohlcv/mnq_continuous
```

## What it does (summary)
1. `dbn` CLI decodes DBN → CSV (ISO timestamps, decimal prices, mapped symbols).
2. DuckDB keeps outright contracts only (drops calendar spreads), selects the
   daily **front month by highest volume**, and writes zstd Parquet partitioned
   by `year=YYYY/month=M`.

Produced dataset: 1.77M rows, 2021-06-24 → 2026-06-24, ~23 MB. See `DATASET.md`.
