import pyarrow.parquet as pq, json, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

LDN = ZoneInfo("Europe/London")
KEEP = {8, 9, 14, 15, 16, 18}   # London hours to KEEP; all others blocked

pf = pq.ParquetFile("run_5yr_initstop.parquet")
trades = json.loads(pf.metadata.metadata[b"trades"])

def parts(iso):
    d = datetime.fromisoformat(iso).astimezone(LDN)
    return d.year, d.hour

rows = [dict(pts=t["pts"], year=parts(t["entry_time"])[0], hour=parts(t["entry_time"])[1]) for t in trades]

def summ(label, g):
    if not g:
        print(f"{label:>16}: (none)"); return
    pts = [r["pts"] for r in g]
    net = sum(pts); wins = sum(1 for p in pts if p > 0)
    top10 = sum(sorted(pts)[-10:])
    print(f"{label:>16}: n={len(g):>3} net={net:>7.0f} median={statistics.median(pts):>6.1f} "
          f"win%={100*wins/len(g):>3.0f} net_ex_top10={net-top10:>7.0f}")

print("=== ALL trades (baseline: init-stop, no hour filter) ===")
summ("baseline", rows)
kept = [r for r in rows if r["hour"] in KEEP]
dropped = [r for r in rows if r["hour"] not in KEEP]
print("\n=== KEEP 08,09,14,15,16,18 LDN ===")
summ("kept", kept)
summ("dropped(blocked)", dropped)

print("\n=== PER-YEAR robustness gate (does KEEP beat baseline each year?) ===")
years = sorted(set(r["year"] for r in rows))
print(f"  {'year':>4} {'base_net':>9} {'keep_net':>9} {'base_n':>6} {'keep_n':>6} {'better?':>7}")
wins_y = 0
for y in years:
    b = [r for r in rows if r["year"] == y]
    k = [r for r in b if r["hour"] in KEEP]
    bn, kn = sum(r["pts"] for r in b), sum(r["pts"] for r in k)
    better = kn > bn
    wins_y += better
    print(f"  {y:>4} {bn:>9.0f} {kn:>9.0f} {len(b):>6} {len(k):>6} {'YES' if better else 'no':>7}")
print(f"\n  KEEP beats baseline in {wins_y}/{len(years)} years")
