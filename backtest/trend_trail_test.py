#!/usr/bin/env python3
"""
Faithful port of trend_strategy.pine (N-floor) detection + exit, built to test
TRAIL variants offline on 5yr MNQ. Goal (user): stop giving back ~$300 (=150pt)
on every winner. Baseline exit = fixed 150pt pullback off the extreme.

Detection (from pine, lines 46-133):
  - olsScan(Nw): OLS slope + r2 over last Nw closes (centered on oldest bar).
  - scan Nw = winMin..winMax step winStep; a window qualifies if
    |slope|*(Nw-1) >= runMinPts and r2 >= minR2; pick BEST r2 (pickBest).
  - latch trend: dir, winN, startPx=close[N-1], extreme=high(up)/low(down).
  - while live: extend extreme; BREAK when close pulls back `pullbackPts` off it.
  - N-floor: only ENTER if winning N >= nFloor. Long side only (default).
  - next-bar fill: pine uses process_orders_on_close=false -> entry/exit fill at
    NEXT bar open. We replicate (enter/exit at next bar's open).

TRAIL variants (only the EXIT rule changes; entries identical):
  fixed:   gap = P always                       (baseline, =150)
  ratchet: once profit(from entry) >= armPts, gap tightens to tightPts;
           before that, gap = P (wide, survive noise)
  scaled:  gap = clamp(P - k*profit, minGap, P)  (linearly tighten with profit)
"""
import csv, os, sys, math
from datetime import datetime, timezone, timedelta

CSV = os.environ.get("BACKTEST_DATA",
    "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv")

def load():
    bars=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            t=row["time"]
            if not t: continue
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError): continue
            bars.append((o,h,l,c))
    return bars

# ---- detection params (pine defaults) ----
WINMIN, WINMAX, WINSTEP = 30, 240, 10
RUNMIN, MINR2 = 150.0, 0.75
NFLOOR = 120
PULLBACK = 150.0
REENTRY_FRAC = 0.7

def ols(closes, end, Nw):
    """OLS over closes[end-Nw+1 .. end]. Returns (slope, r2) or (None,None)."""
    if end - Nw + 1 < 0: return None, None
    yRef = closes[end - (Nw-1)]
    sx=sy=sxx=syy=sxy=0.0
    for i in range(Nw):
        x = float(Nw-1-i)
        y = closes[end - i] - yRef
        sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y
    fN=float(Nw)
    varX=sxx-sx*sx/fN; varY=syy-sy*sy/fN; covXY=sxy-sx*sy/fN
    if varX>0 and varY>0:
        slope=covXY/varX; r2=(covXY*covXY)/(varX*varY)
        return slope, r2
    return None, None

def trail_gap(variant, profit, params):
    """profit = favorable pts from entry so far (>=0). Return current pullback gap."""
    P = params["P"]
    if variant == "fixed":
        return P
    if variant == "ratchet":
        return params["tight"] if profit >= params["arm"] else P
    if variant == "scaled":
        g = P - params["k"] * max(0.0, profit)
        return max(params["minGap"], min(P, g))
    return P

def run(bars, variant="fixed", params=None):
    params = params or {"P": PULLBACK}
    params.setdefault("P", PULLBACK)
    closes=[b[3] for b in bars]
    n=len(bars)
    # trend state
    tState=0; tDir=0; tWinN=None; tExtreme=None; tStartPx=None
    tLockDir=0; tLockExt=None; tLockTrv=None
    # position state (long-only, pyramiding 0)
    pos=0; entry=None; posExtreme=None
    pending=None  # ('enter'|'exit')
    trades=[]  # (entry, exit, pnl_pts, mfe_pts, mae_pts, dur)
    entIdx=None; mfe=0.0; mae=0.0
    for i in range(n):
        o,h,l,c = bars[i]
        # ---- execute pending order at THIS bar open (next-bar fill) ----
        if pending=="enter" and pos==0:
            pos=1; entry=o; posExtreme=o; entIdx=i; mfe=0.0; mae=0.0
        elif pending=="exit" and pos!=0:
            pnl=o-entry
            trades.append((entry,o,pnl,mfe,mae,i-entIdx))
            pos=0; entry=None
        pending=None
        # ---- update open-position excursions + trailing exit test (on this bar) ----
        if pos!=0:
            posExtreme=max(posExtreme,h)
            mfe=max(mfe, h-entry); mae=min(mae, l-entry)
            profit=posExtreme-entry
            gap=trail_gap(variant, profit, params)
            if c < posExtreme - gap:
                pending="exit"
        # ---- clear re-entry lock ----
        if tLockDir!=0 and tLockExt is not None:
            need=REENTRY_FRAC*tLockTrv
            if tLockDir<0 and h>=tLockExt+need: tLockDir=0
            elif tLockDir>0 and l<=tLockExt-need: tLockDir=0
        # ---- trend state machine (uses data through bar i) ----
        if tState==0:
            dS=None;dR=None;dN=None
            wmax=min(WINMAX,1990)
            Nw=WINMIN
            while Nw<=wmax:
                if Nw>=3 and i>=Nw-1:
                    s,r2=ols(closes,i,Nw)
                    if s is not None and abs(s)*float(Nw-1)>=RUNMIN and r2>=MINR2:
                        d=1 if s>0 else -1
                        if d!=tLockDir and (dN is None or r2>dR):
                            dS=s;dR=r2;dN=Nw
                Nw+=WINSTEP
            if dN is not None:
                tState=1; tDir=1 if dS>0 else -1; tWinN=dN
                tStartPx=closes[i-(dN-1)]
                tExtreme=h if tDir>0 else l
                # ENTRY: long-only, N-floor, and not already in a pos
                if tDir>0 and dN>=NFLOOR and pos==0 and tLockDir!=1:
                    pending="enter"
        else:
            tExtreme = max(tExtreme,h) if tDir>0 else min(tExtreme,l)
            broke = (tDir>0 and c<tExtreme-PULLBACK) or (tDir<0 and c>tExtreme+PULLBACK)
            if broke:
                tLockDir=tDir; tLockExt=tExtreme
                tLockTrv=max(abs(tExtreme-tStartPx),1.0)
                tState=0;tDir=0;tWinN=None;tExtreme=None
    return trades

def stats(trades, slip=1.0, label=""):
    if not trades:
        print(f"{label}: no trades"); return
    nets=[t[2]-slip for t in trades]
    mfes=[t[3] for t in trades]
    gross_w=sum(x for x in nets if x>0)
    gross_l=sum(x for x in nets if x<=0)
    net=sum(nets); mfe_sum=sum(mfes)
    wins=sum(1 for x in nets if x>0)
    pf=gross_w/abs(gross_l) if gross_l else float('inf')
    capt=net/mfe_sum*100 if mfe_sum else 0
    print(f"{label:<32} trades={len(trades):>4} net={net:>8.0f}pt "
          f"win%={wins/len(trades)*100:>4.0f} PF={pf:>4.2f} "
          f"MFEsum={mfe_sum:>7.0f} capture={capt:>5.1f}%")

def detect_entries(bars):
    """Run detection ONCE. Return list of entry bar-indices (long-only, N-floor).
    Detection/trend-break uses fixed PULLBACK (independent of the exit trail)."""
    closes=[b[3] for b in bars]; n=len(bars)
    tState=0;tDir=0;tExtreme=None;tStartPx=None
    tLockDir=0;tLockExt=None;tLockTrv=None
    entries=[]
    for i in range(n):
        o,h,l,c=bars[i]
        if tLockDir!=0 and tLockExt is not None:
            need=REENTRY_FRAC*tLockTrv
            if tLockDir<0 and h>=tLockExt+need: tLockDir=0
            elif tLockDir>0 and l<=tLockExt-need: tLockDir=0
        if tState==0:
            dS=None;dR=None;dN=None
            Nw=WINMIN
            while Nw<=min(WINMAX,1990):
                if Nw>=3 and i>=Nw-1:
                    s,r2=ols(closes,i,Nw)
                    if s is not None and abs(s)*float(Nw-1)>=RUNMIN and r2>=MINR2:
                        d=1 if s>0 else -1
                        if d!=tLockDir and (dN is None or r2>dR): dS=s;dR=r2;dN=Nw
                Nw+=WINSTEP
            if dN is not None:
                tState=1;tDir=1 if dS>0 else -1
                tStartPx=closes[i-(dN-1)]; tExtreme=h if tDir>0 else l
                if tDir>0 and dN>=NFLOOR and tLockDir!=1:
                    entries.append(i)  # signal bar; fill next bar open
        else:
            tExtreme=max(tExtreme,h) if tDir>0 else min(tExtreme,l)
            broke=(tDir>0 and c<tExtreme-PULLBACK) or (tDir<0 and c>tExtreme+PULLBACK)
            if broke:
                tLockDir=tDir;tLockExt=tExtreme
                tLockTrv=max(abs(tExtreme-tStartPx),1.0)
                tState=0;tDir=0;tExtreme=None
    return entries

def run_fast(bars, entries, variant, params):
    """Replay each entry with a given trail. Long-only. Fill next bar open.
    A position is opened at entries[k]+1 open; the trail exits when close pulls
    back `gap` off the running high; then we skip any entries during the hold."""
    params=params or {"P":PULLBACK}; params.setdefault("P",PULLBACK)
    n=len(bars); trades=[]; k=0; eset=entries
    ei=0
    while ei<len(eset):
        sig=eset[ei]
        fill=sig+1
        if fill>=n: break
        entry=bars[fill][0]; posExt=entry; mfe=0.0; mae=0.0
        j=fill; exitpx=None
        while j<n:
            o,h,l,c=bars[j]
            posExt=max(posExt,h); mfe=max(mfe,h-entry); mae=min(mae,l-entry)
            gap=trail_gap(variant, posExt-entry, params)
            if c<posExt-gap:
                # exit next bar open
                if j+1<n: exitpx=bars[j+1][0]; exitbar=j+1
                else: exitpx=c; exitbar=j
                break
            j+=1
        if exitpx is None: exitpx=bars[-1][3]; exitbar=n-1
        trades.append((entry,exitpx,exitpx-entry,mfe,mae,exitbar-fill))
        # advance ei past any entries that occurred during the hold
        while ei<len(eset) and eset[ei]<=exitbar: ei+=1
    return trades

if __name__=="__main__":
    print(f"loading {CSV} ...")
    bars=load(); print(f"{len(bars):,} bars, nFloor={NFLOOR}")
    print("detecting entries once...")
    entries=detect_entries(bars); print(f"{len(entries)} raw entry signals")
    for slip in (0.0, 1.0):
        print(f"\n===== slip {slip} pt =====")
        stats(run_fast(bars,entries,"fixed",{"P":150}), slip, "fixed 150 (BASELINE)")
        for arm,tight in [(200,60),(150,40),(100,50),(120,50)]:
            stats(run_fast(bars,entries,"ratchet",{"P":150,"arm":arm,"tight":tight}), slip,
                  f"ratchet arm{arm}->tight{tight}")
        for k,mg in [(0.75,40),(1.0,50),(0.75,50)]:
            stats(run_fast(bars,entries,"scaled",{"P":150,"k":k,"minGap":mg}), slip,
                  f"scaled k{k} min{mg}")
