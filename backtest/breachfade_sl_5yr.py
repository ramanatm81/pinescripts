#!/usr/bin/env python3
"""
5yr test of the BREACH-FADE OVERRIDE mode (slope_strategy.pine build "Galway").

Rule (requires smoothed S/R):
  - Smoothed support/resistance: hold the fractal level flat until a new pivot differs
    by >= smoothSRPct% of price, then snap. (Same as the .pine.)
  - Support breached (low < smSupport)  → enter SHORT exactly breachFadeBars later.
  - Resistance breached (high > smResistance) → enter LONG breachFadeBars later.
  - Exit = next OPPOSITE normal slope signal:
        breach SHORT closes on legSlope < -slopeEntry (long-side signal)
        breach LONG  closes on legSlope >  slopeEntry (short-side signal)
  - NO hard SL. Session/EOD boundaries flatten (fills at close).
  - Fills at signal-bar close (bar-close model). PnL in points.

This is a standalone sim (the breach-fade mode fully replaces the normal exit engine),
reusing the faithful fractal + slope computation from backtest.py's logic.
"""
import csv, sys
from datetime import datetime, timezone, timedelta

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"
SLIP = 1.0

# config — matches the .pine defaults with breach-fade ON
LOOKBACK      = 10
SLOPE_ENTRY   = 2.5
SR_HALF_WIDTH = 10
SMOOTH_SR_PCT = 0.30
BREACH_BARS   = 5
DOJI_PCT      = 10.0
# breach-fade trades now managed like normal slope trades:
SMA_PERIOD    = 9
SL_ABOVE_SMA  = 50.0   # SL pts when close > SMA
SL_BELOW_SMA  = 30.0   # SL pts when close < SMA
TP_PTS        = 50.0
TP_MULT       = 3.0    # TP = 150 pts from entry
# session blocks (CT minutes) — same as slope defaults: LN, preNY, ETH on; NYopen off
def blocked(m):
    return (120 <= m < 150) or (450 <= m < 540) or (1020 <= m < 1050)
def is_eod(m):
    return 900 <= m < 960

def load():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((o,h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars, yrs

def run(bars):
    n=len(bars)
    highs=[]; lows=[]; closes=[]
    slopeBuf=[]
    lastFH=None; lastFL=None
    smHigh=None; smLow=None
    barsSinceSup=None; barsSinceRes=None
    inTrade=False; tradeDir=0; entry=None; activeSL=None; tp=None
    trades=[]  # (dir, entry, exit, pnl)

    def sma():
        return sum(closes[-SMA_PERIOD:])/SMA_PERIOD if len(closes)>=SMA_PERIOD else None

    for bi in range(n):
        o,h,l,c,m = bars[bi]
        highs.append(h); lows.append(l); closes.append(c)
        rng=h-l; bodyPct=(abs(c-o)/rng*100.0) if rng>0 else 0.0
        isDoji=bodyPct<DOJI_PCT
        eod=is_eod(m); inBlk=blocked(m)

        # fractals (confirmed srHalfWidth bars after pivot bar) + smoothed levels
        w=SR_HALF_WIDTH
        if bi>=2*w:
            center=bi-w
            ch=highs[center]
            isPH = all(ch>x for x in highs[bi-2*w:center]) and all(ch>x for x in highs[center+1:bi+1])
            cl=lows[center]
            isPL = all(cl<x for x in lows[bi-2*w:center]) and all(cl<x for x in lows[center+1:bi+1])
            if isPH:
                lastFH=ch
                thr=SMOOTH_SR_PCT/100.0*c
                smHigh = ch if (smHigh is None or abs(ch-smHigh)>=thr) else smHigh
            if isPL:
                lastFL=cl
                thr=SMOOTH_SR_PCT/100.0*c
                smLow = cl if (smLow is None or abs(cl-smLow)>=thr) else smLow

        # breach counters (against smoothed levels)
        supBreach = smLow is not None and l < smLow
        resBreach = smHigh is not None and h > smHigh
        if supBreach: barsSinceSup=0
        elif barsSinceSup is not None: barsSinceSup+=1
        if resBreach: barsSinceRes=0
        elif barsSinceRes is not None: barsSinceRes+=1

        # slope
        legSlope=None
        if not eod and not isDoji:
            slopeBuf.append(c)
            if len(slopeBuf)>LOOKBACK: slopeBuf.pop(0)
        if len(slopeBuf)==LOOKBACK:
            nn=LOOKBACK; sx=sy=sxy=sx2=0.0
            for i in range(nn):
                x=float(i); y=slopeBuf[i]; sx+=x; sy+=y; sxy+=x*y; sx2+=x*x
            denom=nn*sx2-sx*sx
            legSlope=round((nn*sxy-sx*sy)/denom,2) if denom else 0.0

        oppLong  = legSlope is not None and legSlope < -SLOPE_ENTRY   # exits a breach short
        oppShort = legSlope is not None and legSlope >  SLOPE_ENTRY   # exits a breach long
        sessionOK = not eod and not inBlk

        # ---- manage open breach trade: SL/TP intrabar (SL first), then opposite signal ----
        if inTrade:
            exited=False
            # hard SL (intrabar; stop pins the fill)
            if tradeDir==1 and l <= entry-activeSL:
                trades.append((1, entry, entry-activeSL, -activeSL)); inTrade=False; tradeDir=0; entry=None; exited=True
            elif tradeDir==-1 and h >= entry+activeSL:
                trades.append((-1, entry, entry+activeSL, -activeSL)); inTrade=False; tradeDir=0; entry=None; exited=True
            # TP (intrabar limit)
            if not exited:
                if tradeDir==1 and h >= tp:
                    trades.append((1, entry, tp, tp-entry)); inTrade=False; tradeDir=0; entry=None; exited=True
                elif tradeDir==-1 and l <= tp:
                    trades.append((-1, entry, tp, entry-tp)); inTrade=False; tradeDir=0; entry=None; exited=True
            # opposite slope signal (fills at close)
            if not exited:
                if tradeDir==-1 and oppLong:
                    trades.append((-1, entry, c, entry-c)); inTrade=False; tradeDir=0; entry=None; exited=True
                elif tradeDir==1 and oppShort:
                    trades.append((1, entry, c, c-entry)); inTrade=False; tradeDir=0; entry=None; exited=True
            # session/EOD flatten (fills at close)
            if not exited and (eod or inBlk):
                pnl=(c-entry) if tradeDir==1 else (entry-c)
                trades.append((tradeDir, entry, c, pnl)); inTrade=False; tradeDir=0; entry=None

        # 2) ENTER breach trade exactly on the Nth bar. SMA-based SL + 150pt TP (like main).
        shortDue = barsSinceSup is not None and barsSinceSup==BREACH_BARS and sessionOK
        longDue  = barsSinceRes is not None and barsSinceRes==BREACH_BARS and sessionOK
        _sv = sma()
        _slAmt = (SL_BELOW_SMA if (_sv is not None and c < _sv) else SL_ABOVE_SMA)
        if shortDue and tradeDir!=-1:
            if inTrade:  # reverse an open long first
                trades.append((tradeDir, entry, c, (c-entry) if tradeDir==1 else (entry-c)))
            tradeDir=-1; entry=c; inTrade=True; activeSL=_slAmt; tp=c - TP_PTS*TP_MULT
        elif longDue and tradeDir!=1:
            if inTrade:
                trades.append((tradeDir, entry, c, (c-entry) if tradeDir==1 else (entry-c)))
            tradeDir=1; entry=c; inTrade=True; activeSL=_slAmt; tp=c + TP_PTS*TP_MULT

    return trades

def stats(trs):
    pnls=[t[3]-SLIP for t in trs]; n=len(pnls)
    if n==0: return dict(n=0,pnl=0,win=0,pf=0,avg=0,mdd=0,mlose=0)
    pnl=sum(pnls); w=sum(1 for x in pnls if x>0)
    gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
    eq=[]; r=0.0; peak=0.0; mdd=0.0
    for x in pnls:
        r+=x; eq.append(r); peak=max(peak,r); mdd=max(mdd,peak-r)
    ml=cl=0
    for x in pnls:
        cl = cl+1 if x<0 else 0; ml=max(ml,cl)
    return dict(n=n,pnl=round(pnl),win=round(w/n*100,1),
                pf=round(gp/gl,2) if gl>0 else 999, avg=round(pnl/n,2),
                mdd=round(mdd), mlose=ml, biggest_loss=round(min(pnls)))

if __name__=="__main__":
    print("loading 5yr…")
    bars, yrs = load()
    print(f"bars {len(bars):,}  {min(yrs)}-{max(yrs)}\n")
    trs = run(bars)
    st=stats(trs)
    print("=== BREACH-FADE + SL/TP 5yr (SMA stop 30/50, TP 150, opp-signal + session, 1pt slip) ===")
    print(f"pnl={st['pnl']}  win={st['win']}%  n={st['n']}  pf={st['pf']}  avg={st['avg']}")
    print(f"max drawdown={st['mdd']}  max lose streak={st['mlose']}  biggest single loss={st['biggest_loss']}")
    print()
    print("=== per-year ===")
    print("year |   pnl   |  n  | win% | pf   | maxDD  | biggestLoss")
    for yr in range(min(yrs),max(yrs)+1):
        sub=[b for b,y in zip(bars,yrs) if y==yr]
        s=stats(run(sub))
        print(f"{yr} | {s['pnl']:7} | {s['n']:3} | {s['win']:4} | {s['pf']:.2f} | {s['mdd']:6} | {s['biggest_loss']}")
