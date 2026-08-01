"""After a trade loses via SL (Exit-Long/Exit-Short, all pnl<0), IF the next trade
is in the OPPOSITE direction:
  - how many of those next trades won / lost, and net
  - entry-price difference: next entry vs the stopped trade's entry, split by
    whether next entry is ABOVE or BELOW the previous entry, and by how much.

Need entry PRICE too -> read entry rows' Price USD. MNQ 1pt = $2.
"""
import csv, os
from datetime import datetime
from collections import defaultdict

PATH=os.path.expanduser("~/Downloads/input.csv")
rows=list(csv.DictReader(open(PATH,encoding="utf-8-sig")))
bn=defaultdict(dict)
for r in rows:
    num=r["Trade number"].strip(); typ=r["Type"].strip()
    if typ.startswith("Entry"):
        bn[num]["dir"]="L" if "long" in typ else "S"
        bn[num]["entry_px"]=float(r["Price USD"])
        bn[num]["entry_dt"]=r["Date and time"].strip()
    else:
        bn[num]["reason"]=r["Signal"].strip()
        bn[num]["pnl"]=float(r["Net PnL USD"])
tr=[]
for num,d in bn.items():
    if "dir" in d and "reason" in d:
        tr.append(dict(num=int(num),dir=d["dir"],entry_px=d["entry_px"],
                       entry_dt=d["entry_dt"],reason=d["reason"],pnl=d["pnl"]))
tr.sort(key=lambda t:t["num"])

def is_sl(t): return t["reason"] in ("Exit-Long","Exit-Short")

# collect: SL loss -> next trade opposite direction
cases=[]
for i in range(len(tr)-1):
    if is_sl(tr[i]) and tr[i+1]["dir"] != tr[i]["dir"]:
        prev=tr[i]; nxt=tr[i+1]
        diff_px = nxt["entry_px"] - prev["entry_px"]     # + = next entry ABOVE prev
        cases.append(dict(prev=prev, nxt=nxt, diff=diff_px))

n=len(cases)
sl_total=sum(1 for t in tr if is_sl(t))
opp=sum(1 for i in range(len(tr)-1) if is_sl(tr[i]) and tr[i+1]["dir"]!=tr[i]["dir"])
same=sum(1 for i in range(len(tr)-1) if is_sl(tr[i]) and tr[i+1]["dir"]==tr[i]["dir"])
print(f"SL losses total: {sl_total}")
print(f"  next trade OPPOSITE dir: {opp}   (same dir: {same})\n")

# win/loss of the opposite-dir next trades
w=[c for c in cases if c['nxt']['pnl']>0]; l=[c for c in cases if c['nxt']['pnl']<=0]
wp=sum(c['nxt']['pnl'] for c in w); lp=sum(c['nxt']['pnl'] for c in l)
print(f"=== next trade (opposite dir after SL loss): {n} cases ===")
print(f"  WON : {len(w):>3}  net=${wp:>+8.1f}")
print(f"  LOST: {len(l):>3}  net=${lp:>+8.1f}")
print(f"  TOTAL {n:>3}  net=${wp+lp:>+8.1f}  win%={len(w)/n*100:.1f}  avg=${(wp+lp)/n:.2f}\n")

# entry-point difference split
above=[c for c in cases if c['diff']>0]
below=[c for c in cases if c['diff']<0]
same_px=[c for c in cases if abs(c['diff'])<1e-9]
def pts(usd): return usd/2.0   # MNQ price is in points already; diff is in points ($ col is price)
# NOTE: Price USD here is actually the index price (points). diff is in POINTS.
def summ(lst,lab):
    if not lst: print(f"  {lab}: 0"); return
    ds=[c['diff'] for c in lst]
    ww=sum(1 for c in lst if c['nxt']['pnl']>0)
    print(f"  {lab}: {len(lst):>3} cases | entry gap avg={sum(ds)/len(ds):+.1f}pt "
          f"med={sorted(ds)[len(ds)//2]:+.1f}pt max={max(ds,key=abs):+.1f}pt | "
          f"next win%={ww/len(lst)*100:.0f}")
print("=== next entry vs previous entry (points; + = next entry ABOVE prev) ===")
summ(above, "ABOVE (next entry higher)")
summ(below, "BELOW (next entry lower)")
if same_px: summ(same_px,"SAME")

print("\n=== per-case detail ===")
print(f"{'prev entry':>13} {'pd':>2} {'px':>9} -> {'next entry':>13} {'nd':>2} {'px':>9} | {'gap pt':>7} {'dir':>5} | next $")
for c in cases:
    p=c['prev']; x=c['nxt']
    ab = "ABOVE" if c['diff']>0 else ("BELOW" if c['diff']<0 else "SAME")
    print(f"{p['entry_dt'][5:]:>13} {p['dir']:>2} {p['entry_px']:>9.2f} -> "
          f"{x['entry_dt'][5:]:>13} {x['dir']:>2} {x['entry_px']:>9.2f} | "
          f"{c['diff']:>+7.2f} {ab:>5} | {x['pnl']:>+7.1f}")
