import pyarrow.parquet as pq, json, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

pf = pq.ParquetFile("run_5yr_initstop.parquet")
trades = json.loads(pf.metadata.metadata[b"trades"])
t = pf.read(columns=["i", "time", "long_arm", "short_arm"])
i_arr = t["i"].to_pylist(); tm = t["time"].to_pylist()
la = t["long_arm"].to_pylist(); sa = t["short_arm"].to_pylist()

LDN = ZoneInfo("Europe/London")
def hh(iso): return datetime.fromisoformat(iso).astimezone(LDN).hour

rows = []
for tr in trades:
    ei = tr["entry_i"]; armkey = la if tr["dir"] > 0 else sa
    arm_i = next((b for b in range(ei, -1, -1) if armkey[b]), None)
    wait = (ei - arm_i) if arm_i is not None else None
    rows.append(dict(pts=tr["pts"], hour=hh(tr["entry_time"]), wait=wait, dir=tr["dir"]))

net = sum(r["pts"] for r in rows)
print(f"BASE: {len(rows)} trades, net {net:.0f}, median {statistics.median([r['pts'] for r in rows]):.1f}\n")

# --- by ENTRY HOUR (London) ---
print("=== net by ENTRY HOUR (London) — where do small losses cluster? ===")
print(f"  {'hr':>2} {'n':>4} {'net':>8} {'avg':>7} {'win%':>5} {'medianPts':>9}")
for h in range(24):
    g = [r for r in rows if r["hour"] == h]
    if not g: continue
    pts = [r["pts"] for r in g]
    wins = sum(1 for p in pts if p > 0)
    print(f"  {h:>2} {len(g):>4} {sum(pts):>8.0f} {sum(pts)/len(g):>7.1f} {100*wins/len(g):>4.0f}% {statistics.median(pts):>9.1f}")

# --- by WAIT bucket (arm->entry minutes) ---
print("\n=== net by WAIT bucket (arm->entry minutes) ===")
buckets = [(0,15),(15,30),(30,60),(60,120),(120,240),(240,10**9)]
print(f"  {'range':>10} {'n':>4} {'net':>8} {'avg':>7} {'win%':>5} {'median':>7}")
haswait = [r for r in rows if r["wait"] is not None]
for lo, hi in buckets:
    g = [r for r in haswait if lo <= r["wait"] < hi]
    if not g: continue
    pts = [r["pts"] for r in g]; wins = sum(1 for p in pts if p > 0)
    lbl = f"{lo}-{'inf' if hi>10**8 else hi}"
    print(f"  {lbl:>10} {len(g):>4} {sum(pts):>8.0f} {sum(pts)/len(g):>7.1f} {100*wins/len(g):>4.0f}% {statistics.median(pts):>7.1f}")
