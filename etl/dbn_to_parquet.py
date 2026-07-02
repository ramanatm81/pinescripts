#!/usr/bin/env python3
"""
dbn_to_parquet.py — convert a Databento GLBX.MDP3 ohlcv-1m DBN(.zst) file into a
partitioned Parquet dataset of the MNQ continuous FRONT-MONTH series.

Pipeline
--------
1. Decode the DBN to CSV with the `dbn` Rust CLI (pretty timestamps + decimal
   prices + symbol mapping).            ~/.cargo/bin/dbn -C -p -s
2. With DuckDB:
   - keep OUTRIGHT contracts only (symbol has no '-', i.e. drop calendar spreads);
   - pick the daily FRONT contract = highest total volume that trading day
     (rolls ~1 week before expiry as volume migrates to the next quarterly);
   - write partitioned Parquet  year=YYYY/month=M/  (zstd).

No price back-adjustment is applied (small gaps at roll boundaries — fine for
intraday/session-relative strategies). See mnq_continuous/README.md.

Requires: the `dbn` CLI on PATH (or ~/.cargo/bin), and the `duckdb` Python package
(pip install duckdb). The DuckDB CLI is an alternative — see dbn_to_parquet.sh.

Usage:
    python etl/dbn_to_parquet.py INPUT.dbn.zst [OUTPUT_DIR]
    # default OUTPUT_DIR = ./mnq_continuous, temp CSV auto-removed
"""
from __future__ import annotations
import subprocess
import sys
import os
import shutil
from pathlib import Path

DBN_CLI_CANDIDATES = ["dbn", str(Path.home() / ".cargo" / "bin" / "dbn")]


def find_dbn_cli() -> str:
    for c in DBN_CLI_CANDIDATES:
        if shutil.which(c) or Path(c).exists():
            return c
    sys.exit("dbn CLI not found (install: cargo install dbn-cli, or `pip install databento`).")


def decode_to_csv(dbn_cli: str, src: Path, csv_out: Path) -> None:
    print(f"[1/2] decoding {src.name} -> {csv_out.name} (dbn CLI)…")
    # -C csv, -p pretty (ISO ts + decimal px), -s map instrument_id -> symbol, -f overwrite
    subprocess.run([dbn_cli, str(src), "-C", "-p", "-s", "-o", str(csv_out), "-f"], check=True)


def build_parquet(csv_in: Path, out_dir: Path) -> None:
    import duckdb  # local import so the file is importable without duckdb installed
    print(f"[2/2] building continuous front-month parquet -> {out_dir}/ (DuckDB)…")
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          WITH out AS (
            SELECT ts_event, symbol, open, high, low, close, volume,
                   CAST(ts_event AS DATE) AS d
            FROM read_csv_auto('{csv_in.as_posix()}')
            WHERE symbol NOT LIKE '%-%'          -- drop calendar spreads
          ),
          dayvol AS (
            SELECT d, symbol, sum(volume) AS dv,
                   row_number() OVER (PARTITION BY d ORDER BY sum(volume) DESC) AS rn
            FROM out GROUP BY d, symbol
          ),
          front AS (SELECT d, symbol AS front_sym FROM dayvol WHERE rn = 1)
          SELECT o.ts_event, o.symbol, o.open, o.high, o.low, o.close, o.volume,
                 year(o.ts_event)  AS year,
                 month(o.ts_event) AS month
          FROM out o
          JOIN front f ON o.d = f.d AND o.symbol = f.front_sym
          ORDER BY o.ts_event
        )
        TO '{out_dir.as_posix()}'
        (FORMAT parquet, PARTITION_BY (year, month), OVERWRITE_OR_IGNORE, COMPRESSION zstd);
        """
    )
    rows = con.execute(
        f"SELECT count(*), min(ts_event), max(ts_event), count(DISTINCT symbol) "
        f"FROM read_parquet('{out_dir.as_posix()}/**/*.parquet')"
    ).fetchone()
    print(f"    rows={rows[0]:,}  range {rows[1]} -> {rows[2]}  contracts={rows[3]}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    src = Path(argv[0]).expanduser()
    out_dir = Path(argv[1]).expanduser() if len(argv) > 1 else Path("mnq_continuous")
    if not src.exists():
        sys.exit(f"input not found: {src}")

    dbn_cli = find_dbn_cli()
    csv_tmp = src.with_suffix("").with_suffix(".raw.csv")  # e.g. foo.raw.csv
    try:
        decode_to_csv(dbn_cli, src, csv_tmp)
        build_parquet(csv_tmp, out_dir)
    finally:
        if csv_tmp.exists():
            os.remove(csv_tmp)
            print(f"    removed temp {csv_tmp.name}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
