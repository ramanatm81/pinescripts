#!/usr/bin/env python3
"""
5-year TradingView-style performance summary for the Fukuoka slope strategy,
using the faithful port in backtest.py. RAW (0 slippage), to match TV defaults
and the Fukuoka +30,578 headline.

Metrics: net/gross profit, profit factor, max drawdown (points & % of peak equity
proxy), total/win/loss trades, % profitable, avg trade/win/loss, largest win/loss,
equity-curve R^2 (linearity of cumulative equity), per-trade Sharpe (+ annualized),
max consecutive win/loss streaks, avg bars in trade. Plus per-year breakdown.
"""
import csv, math, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, __file__.rsplit("/",1)[0])
import backtest as bt

CSV = "/Users/maheshk81/pinescripts/ohlcv/mnq_5yr.csv"

BASE = dict(slopeEntry=2.5, slAboveSma=50.0, slBelowSma=30.0, tpPts=50.0, tpMult=3.0,
            trailTrigger=30.0, trailDist=8.0, trailDistStrong=10.0,
            tExpBars=20, tExpHardBars=20, tExpHardSlope=1.0,
            cooldownBars=10, cooldownBarsRTH=10)

def load_5yr():
    bars=[]; yrs=[]
    with open(CSV) as f:
        for row in csv.DictReader(f):
            try:
                o=float(row["open"]);h=float(row["high"]);l=float(row["low"]);c=float(row["close"])
            except (ValueError,TypeError,KeyError): continue
            dt=datetime.fromisoformat(row["time"]).astimezone(timezone(timedelta(hours=-5)))
            bars.append((dt,o,h,l,c,dt.hour*60+dt.minute)); yrs.append(dt.year)
    return bars, yrs

def r_squared(equity):
    """R^2 of cumulative equity vs a straight line (linear least-squares fit)."""
    n=len(equity)
    if n<3: return float('nan')
    xs=list(range(n)); mx=sum(xs)/n; my=sum(equity)/n
    sxx=sum((x-mx)**2 for x in xs); sxy=sum((xs[i]-mx)*(equity[i]-my) for i in range(n))
    if sxx==0: return float('nan')
    b=sxy/sxx; a=my-b*mx
    ss_res=sum((equity[i]-(a+b*xs[i]))**2 for i in range(n))
    ss_tot=sum((equity[i]-my)**2 for i in range(n))
    return 1.0 - ss_res/ss_tot if ss_tot>0 else float('nan')

def max_drawdown(equity):
    """Max peak-to-trough drop of the cumulative equity curve, in points."""
    peak=equity[0] if equity else 0.0; mdd=0.0
    for v in equity:
        if v>peak: peak=v
        mdd=max(mdd, peak-v)
    return mdd

def streaks(pnls):
    mw=ml=cw=cl=0
    for x in pnls:
        if x>0: cw+=1; cl=0
        elif x<0: cl+=1; cw=0
        else: cw=0; cl=0
        mw=max(mw,cw); ml=max(ml,cl)
    return mw, ml

def summarize(trades, label):
    # trade tuple: (dir, entry, exit, pnl, reason, deep)
    pnls=[t[3] for t in trades]
    n=len(pnls)
    if n==0:
        print(f"{label}: no trades"); return
    wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
    net=sum(pnls); gp=sum(wins); gl=-sum(losses)
    equity=[]; run=0.0
    for x in pnls: run+=x; equity.append(run)
    mdd=max_drawdown(equity)
    r2=r_squared(equity)
    mean=net/n
    sd=math.sqrt(sum((x-mean)**2 for x in pnls)/n) if n>1 else 0.0
    sharpe_tr = mean/sd if sd>0 else float('nan')
    # ~annualize: trades are spread over 5 years -> trades/year, sqrt scaling
    tpy = n/5.0
    sharpe_ann = sharpe_tr*math.sqrt(tpy) if sd>0 else float('nan')
    mw, ml = streaks(pnls)
    profit_factor = gp/gl if gl>0 else float('inf')

    def fmt(x, d=1): return f"{x:,.{d}f}"
    print(f"===================== {label} =====================")
    print(f"Net profit (pts)            {fmt(net)}")
    print(f"  Gross profit              {fmt(gp)}")
    print(f"  Gross loss               -{fmt(gl)}")
    print(f"Profit factor               {profit_factor:.3f}")
    print(f"Max drawdown (pts)          {fmt(mdd)}")
    print(f"Equity curve R^2            {r2:.4f}")
    print(f"Sharpe (per-trade)          {sharpe_tr:.3f}")
    print(f"Sharpe (annualized*)        {sharpe_ann:.2f}   (*sqrt(trades/yr) scaling, {tpy:.0f} tr/yr)")
    print(f"--")
    print(f"Total trades                {n}")
    print(f"  Winning / Losing          {len(wins)} / {len(losses)}")
    print(f"  Percent profitable        {len(wins)/n*100:.2f}%")
    print(f"Avg trade (pts)             {mean:+.2f}")
    print(f"  Avg win / Avg loss        {(gp/len(wins) if wins else 0):+.2f} / {(-gl/len(losses) if losses else 0):+.2f}")
    print(f"  Win/Loss ratio            {((gp/len(wins))/(gl/len(losses))) if wins and losses else float('nan'):.2f}")
    print(f"Largest win / loss          {max(pnls):+.1f} / {min(pnls):+.1f}")
    print(f"Max consec win / loss       {mw} / {ml}")
    print()

def daily_sharpe(trades):
    """Standard risk-adjusted return: group trade PnL by exit-day, Sharpe of the
    daily-return series, annualized by sqrt(252). Returns (daily_sharpe_ann, ndays)."""
    by_day={}
    for t in trades:
        d=t[6].date()
        by_day[d]=by_day.get(d,0.0)+t[3]
    rets=list(by_day.values()); nd=len(rets)
    if nd<2: return float('nan'), nd
    m=sum(rets)/nd
    sd=math.sqrt(sum((x-m)**2 for x in rets)/(nd-1))
    if sd==0: return float('nan'), nd
    return (m/sd)*math.sqrt(252), nd

def dump_equity(trades, path):
    """Write per-trade cumulative equity + the fitted straight line, for plotting."""
    pnls=[t[3] for t in trades]; eq=[]; r=0.0
    for x in pnls: r+=x; eq.append(r)
    n=len(eq)
    xs=list(range(n)); mx=sum(xs)/n; my=sum(eq)/n
    sxx=sum((x-mx)**2 for x in xs); sxy=sum((xs[i]-mx)*(eq[i]-my) for i in range(n))
    b=sxy/sxx; a=my-b*mx
    # also date-stamp each point for a time axis
    with open(path,"w") as f:
        f.write("i,date,equity,fit\n")
        for i in range(n):
            f.write(f"{i},{trades[i][6].date()},{eq[i]:.1f},{a+b*i:.1f}\n")
    return path

if __name__=="__main__":
    print("loading 5yr…")
    bars, yrs = load_5yr()
    print(f"bars {len(bars):,}  {min(yrs)}-{max(yrs)}  (RAW, 0 slippage)\n")

    all_trades = bt.run(bars, BASE)
    summarize(all_trades, "FULL 5yr (Fukuoka, raw)")

    ds, nd = daily_sharpe(all_trades)
    print(f"Sharpe (daily returns, annualized √252)  {ds:.2f}   over {nd} trading days\n")
    eq_path = dump_equity(all_trades, "/Users/maheshk81/pinescripts/backtest/slope_equity_5yr.csv")
    print(f"equity curve written -> {eq_path}")

    print("===================== per-year (raw) =====================")
    print("year |   net  |  n   | win% |  pf  |  R^2  |  MDD  | maxLoseStrk")
    for yr in range(min(yrs), max(yrs)+1):
        sb=[b for b,y in zip(bars,yrs) if y==yr]
        tr=bt.run(sb, BASE)
        pnls=[t[3] for t in tr]; n=len(pnls)
        if n==0:
            print(f"{yr} | (no trades)"); continue
        net=sum(pnls); w=sum(1 for x in pnls if x>0)
        gp=sum(x for x in pnls if x>0); gl=-sum(x for x in pnls if x<0)
        eq=[]; r=0.0
        for x in pnls: r+=x; eq.append(r)
        _,ml=streaks(pnls)
        print(f"{yr} | {net:6.0f} | {n:4d} | {w/n*100:4.1f} | {(gp/gl if gl>0 else 999):.2f} | "
              f"{r_squared(eq):.3f} | {max_drawdown(eq):5.0f} | {ml}")
