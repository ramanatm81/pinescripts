#!/usr/bin/env python3
"""
5-year walk-forward of ZONE RIDER (zone_rider.pine), ported faithfully to Python.

Purpose: measure the PnL impact of the new exit switch:
  - exitAtLevel = False  -> exit at OPPOSITE ZONE EDGE (resistance+width / support-width)  [default]
  - exitAtLevel = True   -> exit at LEVEL -/+ offset (resistance-10 for longs, support+10 for shorts)

Faithful to the .pine:
  * ta.pivothigh/low(pivotLen,pivotLen): pivot confirmed pivotLen bars AFTER it forms.
  * resistance = last confirmed pivot HIGH, support = last confirmed pivot LOW.
  * SHORT on swingUp (new pivot high >= minSwingPts above prev resistance).
  * LONG  on swingDown (new pivot low <= minSwingPts below prev support).
  * exitOnWick (default True): high/low touch triggers exit; else close-based.
  * Hard SL slPts (default 200) from entry. Cooldown cooldownBars after exit.
  * Session blocks (Chicago mins): EOD 15:00-16:00 flat, LN open, preNY, ETH open.
    (blockNYOpen off by default, matching the .pine defaults.)
  * Bar-close entry model: signal on bar i fills at C[i]; SL/exit managed from
    the NEXT bar onward using that bar's H/L (mirror of calc_on_every_tick=false).

PnL in POINTS, stdlib only. Run with the repo venv or /usr/bin/python3.
"""
import csv, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from strategies import stats

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

# ---- config mirroring the .pine input defaults ----
PIVOT_LEN    = 10
ZONE_WIDTH   = 25.0
MAX_PIVOT_AGE= 0            # 0 = never expire
MIN_SWING    = 50.0
ENABLE_LONG  = True
ENABLE_SHORT = True
COOLDOWN     = 20
EXIT_ON_WICK = True
USE_HARD_SL  = True
SL_PTS       = 200.0
EXIT_OFFSET  = 10.0        # points inside the level when exitAtLevel=True
SLIP         = 1.0         # pts per trade, same convention as wf_5yr.py

# session blocks — Chicago minutes-since-midnight (match .pine defaults)
BLOCK_EOD    = True
BLOCK_NYOPEN = False
BLOCK_LNOPEN = True
BLOCK_PRENY  = True

def load_5yr():
    O=[];H=[];L=[];C=[];TM=[];YR=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError):
                continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))  # Chicago (approx CDT)
            O.append(o);H.append(h);L.append(l);C.append(c)
            TM.append(dt.hour*60+dt.minute); YR.append(dt.year)
    return dict(O=O,H=H,L=L,C=C,TM=TM,YR=YR,n=len(C))

def pivots(series_h, series_l, plen):
    """Causal pivot detection matching ta.pivothigh/low(plen,plen).
    Returns two arrays: on the CONFIRMATION bar i (= pivot_bar + plen), phv[i]/plv[i]
    hold the pivot price (else None). Pivot bar itself is i-plen."""
    n=len(series_h)
    phv=[None]*n; plv=[None]*n
    for i in range(plen, n-plen):
        c=i  # candidate pivot bar
        hv=series_h[c]; lv=series_l[c]
        is_ph=True; is_pl=True
        for j in range(c-plen, c+plen+1):
            if j==c: continue
            if series_h[j]>=hv: is_ph=False
            if series_l[j]<=lv: is_pl=False
            if not is_ph and not is_pl: break
        conf=c+plen  # bar where pivot becomes known
        if is_ph: phv[conf]=hv
        if is_pl: plv[conf]=lv
    return phv, plv

def run(d, exit_at_level):
    """Full Zone Rider state machine + exit engine. Returns list of trade PnLs (pts, pre-slip)."""
    n=d["n"]; O=d["O"];H=d["H"];L=d["L"];C=d["C"];TM=d["TM"]
    phv,plv=pivots(H,L,PIVOT_LEN)

    resistance=None; support=None; resBar=None; supBar=None
    inTrade=False; tradeDir=0; entry=0.0; cooldown=0
    trades=[]

    for i in range(n):
        # session state (Chicago mins)
        m=TM[i]
        eod   = BLOCK_EOD and (900<=m<960)                          # 15:00-16:00
        lnB   = BLOCK_LNOPEN and (120<=m<150)                       # 02:00-02:30
        preNY = BLOCK_PRENY  and (450<=m<540)                       # 07:30-09:00
        nyB   = BLOCK_NYOPEN and (510<=m<540)                       # 08:30-09:00
        ethB  = (1020<=m<1050)                                      # 17:00-17:30 (hardcoded on)
        inBlock = lnB or preNY or nyB or ethB

        # --- manage / flatten open position on THIS bar first (mirrors .pine ordering) ---
        if inTrade:
            # EOD flatten
            if eod:
                px=C[i]; trades.append((px-entry) if tradeDir==1 else (entry-px))
                inTrade=False; tradeDir=0; cooldown=0
            # block flatten
            elif inBlock:
                px=C[i]; trades.append((px-entry) if tradeDir==1 else (entry-px))
                inTrade=False; tradeDir=0; cooldown=0
            else:
                # hard SL (intrabar, checked before target — same as broker stop)
                exited=False
                if USE_HARD_SL:
                    if tradeDir==1 and L[i]<=entry-SL_PTS:
                        trades.append(-SL_PTS); inTrade=False; tradeDir=0; cooldown=COOLDOWN; exited=True
                    elif tradeDir==-1 and H[i]>=entry+SL_PTS:
                        trades.append(-SL_PTS); inTrade=False; tradeDir=0; cooldown=COOLDOWN; exited=True
                # target exit
                if not exited:
                    resValid = resistance is not None and (MAX_PIVOT_AGE==0 or (resBar is not None and i-resBar<=MAX_PIVOT_AGE))
                    supValid = support   is not None and (MAX_PIVOT_AGE==0 or (supBar is not None and i-supBar<=MAX_PIVOT_AGE))
                    if tradeDir==1 and resValid:
                        lvl = (resistance-EXIT_OFFSET) if exit_at_level else (resistance+ZONE_WIDTH)
                        hit = (H[i]>=lvl) if EXIT_ON_WICK else (C[i]>=lvl)
                        if hit:
                            px = lvl if EXIT_ON_WICK else C[i]
                            trades.append(px-entry); inTrade=False; tradeDir=0; cooldown=COOLDOWN
                    elif tradeDir==-1 and supValid:
                        lvl = (support+EXIT_OFFSET) if exit_at_level else (support-ZONE_WIDTH)
                        hit = (L[i]<=lvl) if EXIT_ON_WICK else (C[i]<=lvl)
                        if hit:
                            px = lvl if EXIT_ON_WICK else C[i]
                            trades.append(entry-px); inTrade=False; tradeDir=0; cooldown=COOLDOWN

        # --- pivot updates + swing signals on THIS bar ---
        swingUp=False; swingDown=False
        if phv[i] is not None:
            prev=resistance
            resistance=phv[i]; resBar=i-PIVOT_LEN
            if prev is not None and (phv[i]-prev)>=MIN_SWING: swingUp=True
        if plv[i] is not None:
            prev=support
            support=plv[i]; supBar=i-PIVOT_LEN
            if prev is not None and (prev-plv[i])>=MIN_SWING: swingDown=True

        # cooldown tick
        if cooldown>0 and not inTrade: cooldown-=1

        # --- entry gate (bar-close fill) ---
        canEnter = (not inTrade) and (not eod) and (not inBlock) and cooldown==0
        if canEnter:
            if ENABLE_LONG and swingDown:
                inTrade=True; tradeDir=1; entry=C[i]
            elif ENABLE_SHORT and swingUp:
                inTrade=True; tradeDir=-1; entry=C[i]

    return trades

def adj(tr): return [t-SLIP for t in tr]

def report(label, d):
    tr=adj(run(d, exit_at_level=(label=="ON")))
    st=stats(tr)
    print(f"{label:>3} | pnl={st['pnl']:9.0f} | win {st['winrate']:4.0f}% | n {st['n']:5d} | pf {st['pf']:.2f} | avg {st['avg']:+.2f}")
    return st

def per_year(d, exit_at_level):
    rows=[]
    for yr in range(min(d['YR']), max(d['YR'])+1):
        idx=[i for i in range(d['n']) if d['YR'][i]==yr]
        sub={k:[d[k][i] for i in idx] for k in ("O","H","L","C","TM","YR")}
        sub["n"]=len(idx)
        st=stats(adj(run(sub, exit_at_level)))
        rows.append((yr,st))
    return rows

if __name__=="__main__":
    print("loading 5yr…")
    d=load_5yr()
    print(f"bars {d['n']:,}  {min(d['YR'])}-{max(d['YR'])}\n")

    print("=== FULL 5yr (1pt slip/trade) ===")
    print("mode| exit rule")
    print("OFF | opposite ZONE EDGE  (long: resistance+25 | short: support-25)")
    print("ON  | LEVEL -/+ offset    (long: resistance-10 | short: support+10)\n")
    off=report("OFF", d)
    on =report("ON",  d)

    print("\n=== per-year: OFF (zone edge) ===")
    print("year |   pnl   | win% |  n  | pf")
    for yr,st in per_year(d, False):
        print(f"{yr} | {st['pnl']:7.0f} | {st['winrate']:4.0f} | {st['n']:3d} | {st['pf']:.2f}")

    print("\n=== per-year: ON (level -/+ 10) ===")
    print("year |   pnl   | win% |  n  | pf")
    for yr,st in per_year(d, True):
        print(f"{yr} | {st['pnl']:7.0f} | {st['winrate']:4.0f} | {st['n']:3d} | {st['pf']:.2f}")

    d_pnl = on['pnl']-off['pnl']
    print(f"\nDELTA (ON - OFF): {d_pnl:+.0f} pts over 5yr  ({d_pnl/5:+.0f}/yr)")
