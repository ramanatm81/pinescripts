import pyarrow.parquet as pq, json, statistics

pf = pq.ParquetFile("run_oos.parquet")
trades = json.loads(pf.metadata.metadata[b"trades"])
t = pf.read(columns=["i", "long_arm", "short_arm"])
i_arr = t["i"].to_pylist(); la = t["long_arm"].to_pylist(); sa = t["short_arm"].to_pylist()

rows = []
for tr in trades:
    ei = tr["entry_i"]; armkey = la if tr["dir"] > 0 else sa
    arm_i = next((b for b in range(ei, -1, -1) if armkey[b]), None)
    if arm_i is None: continue
    rows.append(dict(wait=ei - arm_i, pts=tr["pts"]))

def summ(label, grp):
    pts = [g["pts"] for g in grp]
    wins = [p for p in pts if p > 0]
    med = statistics.median(pts)
    net = sum(pts)
    # net excluding the single best trade -> how tail-dependent is it?
    net_ex = net - max(pts)
    print(f"{label:>10} n={len(grp):>2}  net={net:>7.0f}  MEDIAN={med:>6.1f}  win%={100*len(wins)/len(grp):>3.0f}  "
          f"net_ex_top={net_ex:>7.0f}  best={max(pts):>6.0f}")

rows.sort(key=lambda r: r["wait"])
n = len(rows); third = n // 3
print("=== terciles ===")
summ("fast", rows[:third])
summ("mid", rows[third:2*third])
summ("slow", rows[2*third:])

print("\n=== simple split: fast/mid (<=95min) vs slow (>95min) ===")
fastmid = [r for r in rows if r["wait"] <= 95]
slow = [r for r in rows if r["wait"] > 95]
summ("<=95min", fastmid)
summ(">95min", slow)

print("\n=== every trade is a loser? median test across ALL 33 ===")
allpts = [r["pts"] for r in rows]
print(f"  all: median={statistics.median(allpts):.1f}  mean={statistics.mean(allpts):.1f}  "
      f"net={sum(allpts):.0f}  win%={100*sum(1 for p in allpts if p>0)/len(allpts):.0f}")
print(f"  losers: {sum(1 for p in allpts if p<=0)} / {len(allpts)}")
print(f"  net without the single best trade: {sum(allpts)-max(allpts):.0f}")
print(f"  net without top 3: {sum(sorted(allpts)[:-3]):.0f}")
