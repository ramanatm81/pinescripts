"""Inter-trade gaps on the REAL TV export (~/Downloads/input.csv).
Gap = time from trade A EXIT to trade B ENTRY. SESSION-FILTER idle time is
EXCLUDED: any minute inside a block window is not counted toward the gap, so a
big gap means a genuine no-signal pause, not the strategy being session-blocked.

Session blocks (CT, from slope_strategy.pine):
  LNOpen  02:00-02:30   PreNY 07:30-09:00   ETH 23:00-23:30
  EOD/close 15:00-16:00 (eodClose; no entries)
Times in the export are naive LONDON (chart tz); convert to CT (London=UTC+1 BST,
CT=UTC-5 in this data -> CT = London - 6h) to test the windows.
"""
import csv, os
from datetime import datetime, timedelta
from collections import defaultdict

PATH = os.path.expanduser("~/Downloads/input.csv")
rows = list(csv.DictReader(open(PATH, encoding="utf-8-sig")))
by_num = defaultdict(dict)
for r in rows:
    num = r["Trade number"].strip(); typ = r["Type"].strip()
    dt = datetime.strptime(r["Date and time"].strip(), "%Y-%m-%d %H:%M")  # London naive
    rec = dict(dt=dt, signal=r["Signal"].strip(), pnl=float(r["Net PnL USD"]))
    if typ.startswith("Entry"):
        by_num[num]["entry"]=rec; by_num[num]["dir"]="L" if "long" in typ else "S"
    else:
        by_num[num]["exit"]=rec
trades=[]
for num,d in by_num.items():
    if "entry" in d and "exit" in d:
        trades.append(dict(num=int(num), dir=d["dir"],
                           entry=d["entry"]["dt"], exit=d["exit"]["dt"],
                           reason=d["exit"]["signal"], pnl=d["exit"]["pnl"]))
trades.sort(key=lambda t:t["num"])

def ct(dt):  # London -> CT (minus 6h in this dataset)
    return dt - timedelta(hours=6)

def blocked(ct_dt):
    m = ct_dt.hour*60 + ct_dt.minute
    return (120 <= m < 150) or (450 <= m < 540) or (1380 <= m < 1410) or (900 <= m < 960)

def blocked_minutes(a, b):
    """count session-blocked minutes in [a,b) by stepping minute-by-minute (CT)."""
    if b <= a: return 0
    n = 0; cur = a.replace(second=0, microsecond=0)
    while cur < b:
        if blocked(ct(cur)): n += 1
        cur += timedelta(minutes=1)
    return n

# build gaps: exit[i] -> entry[i+1], minus blocked minutes in that window
gaps = []
for i in range(len(trades)-1):
    a_exit = trades[i]["exit"]; b_entry = trades[i+1]["entry"]
    raw = (b_entry - a_exit).total_seconds()/60.0
    if raw < 0:  # overlapping/next-bar re-entry oddities
        continue
    blk = blocked_minutes(a_exit, b_entry)
    net = raw - blk
    gaps.append(dict(idx=i, raw=raw, blk=blk, net=max(net,0.0),
                     from_exit=a_exit, to_entry=b_entry,
                     next_dir=trades[i+1]["dir"], next_pnl=trades[i+1]["pnl"],
                     next_reason=trades[i+1]["reason"]))

netvals = sorted(g["net"] for g in gaps)
n = len(netvals)
def pct(p): return netvals[int(p/100*(n-1))]
print(f"gaps measured: {n}  (exit->next entry, session-blocked minutes removed)")
print(f"  median={pct(50):.0f}m  mean={sum(netvals)/n:.1f}m  "
      f"p90={pct(90):.0f}m  p95={pct(95):.0f}m  max={netvals[-1]:.0f}m\n")

buckets = [(0,10),(10,30),(30,60),(60,120),(120,10**9)]
labels  = ["<10m","10-30m","30-60m","60-120m","120m+"]
print("distribution (NET gap, session idle excluded):")
for (lo,hi),lab in zip(buckets,labels):
    c = sum(1 for v in netvals if lo <= v < hi)
    print(f"  {lab:>8}: {c:>4}  ({c/n*100:4.1f}%)")

print("\n20 biggest REAL gaps (after excluding session-block idle):")
print(f"{'from exit (LDN)':>16} -> {'to entry (LDN)':>16} | {'raw':>6} {'blk':>5} {'NET':>6} | next")
for g in sorted(gaps, key=lambda g:-g["net"])[:20]:
    print(f"{g['from_exit'].strftime('%m-%d %H:%M'):>16} -> "
          f"{g['to_entry'].strftime('%m-%d %H:%M'):>16} | "
          f"{g['raw']:>5.0f}m {g['blk']:>4.0f}m {g['net']:>5.0f}m | "
          f"{g['next_dir']} {g['next_pnl']:+.1f} [{g['next_reason']}]")
