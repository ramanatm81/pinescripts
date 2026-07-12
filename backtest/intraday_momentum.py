#!/usr/bin/env python3
"""
Gao, Han, Li & Zhou (2018) "Market Intraday Momentum" — tested on NQ/MNQ 5yr.
Rule (RTH 09:30-16:00 ET, 13 half-hours):
  r1  = first half-hour return   (prior RTH close -> 10:00 ET)   [close_1000 / close_prev_rth - 1]
  r12 = penultimate half-hour    (15:00 -> 15:30 ET return)
  At 15:30 ET: enter the LAST half-hour (15:30->16:00) WITH the signal, flat at 16:00.
    variant A: trade sign(r1)
    variant B: trade sign(r1) only if sign(r1)==sign(r12)  (stronger per paper)
  One trade/day. Honest costs: subtract round-trip COST pts/trade (sweep 0/2/4).
  Report per year: pnl(pts), n trades, win%, avg pts/trade, Sharpe(daily).

Data UTC -> America/New_York (DST-correct) via zoneinfo. NQ point = $ per pt (report in pts).
"""
import csv, math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
NY  = ZoneInfo("America/New_York")

def load():
    rows = []
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                c = float(row["close"])
            except (ValueError, KeyError):
                continue
            dt_utc = datetime.fromisoformat(row["time"])
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            dt = dt_utc.astimezone(NY)
            rows.append((dt, c))
    return rows

def minute_of_day(dt):
    return dt.hour * 60 + dt.minute

# RTH session boundaries in ET minutes-since-midnight
OPEN   = 9*60 + 30    # 570  09:30
T1000  = 10*60        # 600  10:00 (end of first half-hour)
T1500  = 15*60        # 900  15:00
T1530  = 15*60 + 30   # 930  15:30
CLOSE  = 16*60        # 960  16:00

def build_days(rows):
    """Group bars by ET trading date; keep RTH closes we need per day."""
    days = {}  # date -> dict of needed closes
    for dt, c in rows:
        d = dt.date()
        m = minute_of_day(dt)
        if m < OPEN or m > CLOSE:
            continue  # RTH only
        rec = days.setdefault(d, {})
        # last RTH close of the day (for prev-day close reference) = close at/just-before 16:00
        rec['last_rth'] = c            # overwritten through the day -> ends as ~15:59 close
        rec['last_rth_min'] = m
        if m <= T1000:
            rec['c1000'] = c; rec['c1000_min'] = m      # ~10:00 close (last bar <=10:00)
        if m <= T1500:
            rec['c1500'] = c
        if m <= T1530:
            rec['c1530'] = c
        # close nearest 16:00 handled by last_rth
    return days

def run(days, cost_pts, variant):
    dates = sorted(days.keys())
    trades = []  # (date, dir, pnl_pts)
    prev_close = None
    for d in dates:
        rec = days[d]
        # need a full RTH day
        need = ('c1000','c1500','c1530','last_rth')
        if not all(k in rec for k in need):
            prev_close = rec.get('last_rth', prev_close)
            continue
        if prev_close is None:
            prev_close = rec['last_rth']
            continue
        r1  = rec['c1000'] / prev_close - 1.0       # first half-hour
        r12 = rec['c1530'] / rec['c1500'] - 1.0     # penultimate half-hour (15:00->15:30)
        sig = 0
        if variant == 'A':
            sig = 1 if r1 > 0 else (-1 if r1 < 0 else 0)
        else:  # B: require agreement
            s1 = 1 if r1 > 0 else (-1 if r1 < 0 else 0)
            s12 = 1 if r12 > 0 else (-1 if r12 < 0 else 0)
            sig = s1 if (s1 != 0 and s1 == s12) else 0
        if sig != 0:
            # trade the last half-hour: enter at 15:30 close, exit at 16:00 close
            move = rec['last_rth'] - rec['c1530']   # points
            pnl = sig * move - cost_pts
            trades.append((d, sig, pnl))
        prev_close = rec['last_rth']
    return trades

def stats(trades):
    if not trades:
        return dict(n=0, pnl=0, win=0.0, avg=0.0, sharpe=0.0)
    pnls = [t[2] for t in trades]
    n = len(pnls); tot = sum(pnls)
    w = sum(1 for x in pnls if x > 0)
    mean = tot / n
    var = sum((x-mean)**2 for x in pnls) / n
    sd = math.sqrt(var) if var > 0 else 0.0
    sharpe = (mean / sd * math.sqrt(252)) if sd > 0 else 0.0   # ~1 trade/day -> annualize by 252
    return dict(n=n, pnl=round(tot), win=round(100*w/n,1), avg=round(mean,2), sharpe=round(sharpe,2))

if __name__ == "__main__":
    print("loading + NY conversion…")
    rows = load()
    days = build_days(rows)
    yrs = sorted({d.year for d in days})
    print(f"trading days: {len(days):,}   years: {yrs}\n")
    for variant in ['A', 'B']:
        label = "A: sign(r1)" if variant=='A' else "B: sign(r1)==sign(r12)"
        print(f"########## Variant {label} ##########")
        for cost in [0.0, 2.0, 4.0]:
            trades = run(days, cost, variant)
            s = stats(trades)
            byyr = []
            for y in yrs:
                sy = stats([t for t in trades if t[0].year == y])
                byyr.append(sy['pnl'])
            pos = sum(1 for x in byyr if x > 0)
            print(f"  cost {cost:>3.0f}pt | pnl {s['pnl']:>6} n {s['n']:>4} win {s['win']:>5}% avg {s['avg']:>6} sharpe {s['sharpe']:>5} | {pos}/{len(yrs)}yr | {byyr}")
        print()
