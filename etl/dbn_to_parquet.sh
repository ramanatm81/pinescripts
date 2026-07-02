#!/usr/bin/env bash
# dbn_to_parquet.sh — exact CLI pipeline used to build the MNQ continuous
# front-month parquet dataset. No Python needed: just the `dbn` Rust CLI and
# the DuckDB CLI. This is the shell equivalent of dbn_to_parquet.py.
#
# Usage: ./dbn_to_parquet.sh INPUT.dbn.zst [OUTPUT_DIR]
set -euo pipefail

SRC="${1:?usage: dbn_to_parquet.sh INPUT.dbn.zst [OUTPUT_DIR]}"
OUT="${2:-mnq_continuous}"
DBN="${DBN_CLI:-$HOME/.cargo/bin/dbn}"
CSV="_dbn_raw.csv"

echo "[1/2] decoding $SRC -> $CSV"
"$DBN" "$SRC" -C -p -s -o "$CSV" -f    # csv, pretty ts/px, map symbols, overwrite

echo "[2/2] continuous front-month parquet -> $OUT/"
duckdb -c "
COPY (
  WITH out AS (
    SELECT ts_event, symbol, open, high, low, close, volume, CAST(ts_event AS DATE) AS d
    FROM read_csv_auto('$CSV')
    WHERE symbol NOT LIKE '%-%'          -- drop calendar spreads
  ),
  dayvol AS (
    SELECT d, symbol, sum(volume) AS dv,
           row_number() OVER (PARTITION BY d ORDER BY sum(volume) DESC) AS rn
    FROM out GROUP BY d, symbol
  ),
  front AS (SELECT d, symbol AS front_sym FROM dayvol WHERE rn = 1)
  SELECT o.ts_event, o.symbol, o.open, o.high, o.low, o.close, o.volume,
         year(o.ts_event) AS year, month(o.ts_event) AS month
  FROM out o JOIN front f ON o.d = f.d AND o.symbol = f.front_sym
  ORDER BY o.ts_event
)
TO '$OUT'
(FORMAT parquet, PARTITION_BY (year, month), OVERWRITE_OR_IGNORE, COMPRESSION zstd);
"

rm -f "$CSV"
echo "done -> $OUT/"
duckdb -c "SELECT count(*) AS rows, min(ts_event) AS first, max(ts_event) AS last,
                  count(DISTINCT symbol) AS contracts
           FROM read_parquet('$OUT/**/*.parquet');"
