"""On the REAL TV export: simulate 'skip the entry immediately after 2 consecutive
TRAIL wins, then resume' and measure net vs the actual book.

Logic (skip-one-then-resume): walk trades in order, maintaining a count of
consecutive TRAIL wins among *taken* trades. When count==2, the NEXT taken
trade is skipped; skipping resets the count to 0 (the skipped trade is not a
win, and we resume fresh). A taken non-trail-win also resets count to 0.
"""
import csv, os
from collections import defaultdict

PATH = os.path.expanduser("~/Downloads/input.csv")
rows = list(csv.DictReader(open(PATH, encoding="utf-8-sig")))
by_num = defaultdict(dict)
for r in rows:
    num = r["Trade number"].strip(); typ = r["Type"].strip()
    rec = dict(dt=r["Date and time"].strip(), signal=r["Signal"].strip(),
               pnl=float(r["Net PnL USD"]))
    if typ.startswith("Entry"):
        by_num[num]["entry"]=rec; by_num[num]["dir"]="L" if "long" in typ else "S"
    else:
        by_num[num]["exit"]=rec
trades=[]
for num,d in by_num.items():
    if "entry" in d and "exit" in d:
        trades.append(dict(num=int(num), dir=d["dir"],
                           entry_dt=d["entry"]["dt"],
                           reason=d["exit"]["signal"], pnl=d["exit"]["pnl"]))
trades.sort(key=lambda t:t["num"])

def is_tw(t): return t["reason"]=="TRAIL" and t["pnl"]>0

# baseline
base_net = sum(t["pnl"] for t in trades)
base_n   = len(trades)

# simulate skip-one-then-resume
count=0; taken=[]; skipped=[]
for t in trades:
    if count==2:
        skipped.append(t)   # skip this entry
        count=0             # resume fresh
        continue
    taken.append(t)
    count = count+1 if is_tw(t) else 0

new_net = sum(t["pnl"] for t in taken)
sk_net  = sum(t["pnl"] for t in skipped)
sk_w    = sum(1 for t in skipped if t["pnl"]>0)

print(f"BASELINE (real):  trades={base_n}  net={round(base_net,1)} USD  "
      f"win%={round(sum(1 for t in trades if t['pnl']>0)/base_n*100,1)}")
print(f"SKIP-3rd rule:    trades={len(taken)}  net={round(new_net,1)} USD  "
      f"win%={round(sum(1 for t in taken if t['pnl']>0)/len(taken)*100,1)}")
print(f"  -> skipped {len(skipped)} trades worth {round(sk_net,1)} USD "
      f"({sk_w}W / {len(skipped)-sk_w}L, win%={round(sk_w/len(skipped)*100,1)})")
print(f"  -> NET IMPACT of the rule: {round(new_net-base_net,+1):+} USD")
print()
print("The skipped trades (the '3rd' after 2 trail wins):")
print(f"{'entry':>16} {'d':>1} {'pnl':>8} {'exit':>10}")
for t in skipped:
    print(f"{t['entry_dt']:>16} {t['dir']:>1} {t['pnl']:>+8.1f} {t['reason']:>10}")
