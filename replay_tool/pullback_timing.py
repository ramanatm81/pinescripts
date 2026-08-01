import pyarrow.parquet as pq, json, statistics

PATH = "run_oos.parquet"
pf = pq.ParquetFile(PATH)
trades = json.loads(pf.metadata.metadata[b"trades"])
t = pf.read(columns=["i", "time", "long_arm", "short_arm", "entry_dir"])
i_arr = t["i"].to_pylist()
la = t["long_arm"].to_pylist()
sa = t["short_arm"].to_pylist()
ed = t["entry_dir"].to_pylist()

rows = []
for k, tr in enumerate(trades):
    ei = tr["entry_i"]
    armkey = la if tr["dir"] > 0 else sa
    arm_i = None
    for b in range(ei, -1, -1):
        if armkey[b]:
            arm_i = b
            break
    if arm_i is None:
        continue
    wait = ei - arm_i  # 1-min bars = minutes from arm(identification) to entry(pullback confirmed)
    rows.append(dict(k=k + 1, dir="L" if tr["dir"] > 0 else "S", wait=wait,
                     pts=tr["pts"], mfe=tr["mfe"], mae=tr["mae"],
                     bars_held=tr["bars_held"], reason=tr["reason"]))

rows.sort(key=lambda r: r["wait"])
print(f"{len(rows)} trades with an arm found (of {len(trades)})\n")
print("per-trade: wait(min) = arm->entry, then result")
print(f"  {'#':>3} {'dir':>3} {'wait':>5} {'pts':>8} {'mfe':>6} {'mae':>7} {'held':>5} {'reason':>8}")
for r in rows:
    print(f"  {r['k']:>3} {r['dir']:>3} {r['wait']:>5} {r['pts']:>8.1f} {r['mfe']:>6.0f} {r['mae']:>7.0f} {r['bars_held']:>5} {r['reason']:>8}")

waits = [r["wait"] for r in rows]
print(f"\nWAIT (arm->entry) minutes:  min {min(waits)}  median {statistics.median(waits):.0f}  "
      f"mean {statistics.mean(waits):.0f}  max {max(waits)}")

# does a faster/slower pullback predict a better result? bucket by wait tercile
rows_by_wait = sorted(rows, key=lambda r: r["wait"])
n = len(rows_by_wait)
third = n // 3
buckets = [("fast", rows_by_wait[:third]),
           ("mid", rows_by_wait[third:2 * third]),
           ("slow", rows_by_wait[2 * third:])]
print("\nresult by pullback-speed tercile:")
print(f"  {'bucket':>6} {'n':>3} {'waitRange':>12} {'net pts':>9} {'avg pts':>8} {'win%':>6}")
for name, grp in buckets:
    if not grp:
        continue
    ws = [g["wait"] for g in grp]
    net = sum(g["pts"] for g in grp)
    wins = sum(1 for g in grp if g["pts"] > 0)
    print(f"  {name:>6} {len(grp):>3} {f'{min(ws)}-{max(ws)}':>12} {net:>9.1f} {net/len(grp):>8.1f} "
          f"{100*wins/len(grp):>5.0f}%")

# correlation wait vs pts
if len(rows) > 2:
    try:
        r = statistics.correlation(waits, [x["pts"] for x in rows])
        print(f"\ncorrelation(wait, pts) = {r:+.2f}  (>0: slower pullback -> better; <0: faster better)")
    except Exception as e:
        print("corr n/a:", e)
