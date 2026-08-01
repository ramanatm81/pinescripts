"""Parse the REAL TradingView strategy export (~/Downloads/input.csv) into
round-trip trades, then run the '3 consecutive TRAIL wins -> next trade' study
on the ACTUAL trades (not the python port).

TV export: 2 rows per trade sharing 'Trade number'. Entry row has the entry
signal (S up / S down); Exit row's Signal is the exit reason and its Net PnL
is the trade PnL. Times are naive local = London (chart tz).
"""
import csv, os
from collections import defaultdict

PATH = os.path.expanduser("~/Downloads/input.csv")

rows = []
with open(PATH, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append(r)

# group by trade number
by_num = defaultdict(dict)
for r in rows:
    num = r["Trade number"].strip()
    typ = r["Type"].strip()
    rec = dict(dt=r["Date and time"].strip(),
               signal=r["Signal"].strip(),
               price=float(r["Price USD"]),
               pnl=float(r["Net PnL USD"]))
    if typ.startswith("Entry"):
        by_num[num]["entry"] = rec
        by_num[num]["dir"] = "L" if "long" in typ else "S"
    else:
        by_num[num]["exit"] = rec

# build ordered trade list (by entry time)
trades = []
for num, d in by_num.items():
    if "entry" not in d or "exit" not in d:
        continue
    trades.append(dict(
        num=int(num),
        dir=d["dir"],
        entry_dt=d["entry"]["dt"],
        exit_dt=d["exit"]["dt"],
        reason=d["exit"]["signal"],   # exit reason lives on exit row
        pnl=d["exit"]["pnl"],
    ))
trades.sort(key=lambda t: t["num"])

print(f"parsed {len(trades)} round-trip trades")
print(f"span: {trades[0]['entry_dt']} -> {trades[-1]['entry_dt']}")
wins = sum(1 for t in trades if t["pnl"] > 0)
print(f"win%={round(wins/len(trades)*100,1)}  net={round(sum(t['pnl'] for t in trades),1)} USD")
print(f"exit-reason counts: ", end="")
rc = defaultdict(int)
for t in trades: rc[t["reason"]] += 1
print(dict(sorted(rc.items(), key=lambda kv:-kv[1])))

def is_trail_win(t):
    return t["reason"] == "TRAIL" and t["pnl"] > 0

def study(K):
    nexts = []
    for i in range(K, len(trades)):
        if all(is_trail_win(trades[i-j]) for j in range(1, K+1)):
            nexts.append(trades[i])
    n = len(nexts)
    if n == 0:
        print(f"\nK={K}: no occurrences"); return
    w = [t for t in nexts if t["pnl"] > 0]
    l = [t for t in nexts if t["pnl"] <= 0]
    wp, lp = sum(t["pnl"] for t in w), sum(t["pnl"] for t in l)
    print(f"\n===== NEXT trade after {K} consecutive TRAIL wins (REAL TV trades) =====")
    print(f"  occurrences: {n}")
    print(f"    winners: {len(w):>3}  pnl={round(wp,1):>9} USD")
    print(f"    losers : {len(l):>3}  pnl={round(lp,1):>9} USD")
    print(f"    TOTAL  : {n:>3}  pnl={round(wp+lp,1):>9} USD  "
          f"win%={round(len(w)/n*100,1)}  avg={round((wp+lp)/n,2)}")

study(2); study(3)

# print the K=3 table
K=3
print(f"\n=== 3-TRAIL-WIN sequences (REAL) ===")
print(f"{'#':>3} | {'win1':>16} {'win2':>16} {'win3':>16} || {'NEXT':>16} {'d':>1} {'pnl':>8} {'exit':>6} res")
cnt=0
for i in range(K, len(trades)):
    if all(is_trail_win(trades[i-j]) for j in (1,2,3)):
        cnt+=1
        a,b,c,x = trades[i-3],trades[i-2],trades[i-1],trades[i]
        res = "WIN" if x["pnl"]>0 else "LOSS"
        print(f"{cnt:>3} | {a['entry_dt']:>16} {b['entry_dt']:>16} {c['entry_dt']:>16} || "
              f"{x['entry_dt']:>16} {x['dir']:>1} {x['pnl']:>+8.1f} {x['reason']:>6} {res}")
print(f"total: {cnt}")
