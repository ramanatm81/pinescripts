#!/usr/bin/env python3
"""CLEAN v2 Support-Ride port. Rebuilt with:
  - pytz America/Chicago (DST-aware) CT conversion  [fixes the fixed -5 offset bug]
  - ONLY three session blocks: LN-open, preNY/NY-open, EOD.  Lunch/ETH-open/Asia REMOVED.

Long leg only. Entry: close in [support-ride, support+ride] AND support<resistance
AND spread<=maxSpread. Exit: broker TP limit (entry+tp) + broker stop max(support-zone, entry-maxStop).
Cooldown N flat bars after exit. Fills: entry next-bar-open; TP/stop intrabar (gap fills at open).
"""
import os, csv, sys
import pytz
from datetime import datetime

DATA = os.environ.get("BACKTEST_DATA",
                      os.path.join(os.path.dirname(__file__), "..", "ohlcv", "mnq_5yr.csv"))
CHI = pytz.timezone("America/Chicago")

# ---- ONLY these blocks remain (CT minutes since midnight) ----
# LN open : 02:00-02:30 CT  (120-150)
# preNY   : 07:30-09:00 CT  (450-540)  -- spans the NY open
# EOD     : 15:00-16:00 CT  (900-960)  -- flatten window
def blocked(ctm):
    if 120 <= ctm < 150: return True   # LN open
    if 450 <= ctm < 540: return True   # preNY + NY open
    if 900 <= ctm < 960: return True   # EOD
    return False

def load(path):
    bars = []
    for row in csv.DictReader(open(path)):
        t = row["time"]
        if not t: continue
        try:
            o=float(row["open"]); h=float(row["high"]); l=float(row["low"]); c=float(row["close"])
            v=float(row.get("Volume", 0) or 0)
        except (ValueError, TypeError):
            continue
        # parse tz-aware, convert to America/Chicago with real DST rules
        dt = datetime.fromisoformat(t).astimezone(CHI)
        ctm = dt.hour*60 + dt.minute
        bars.append((dt, o, h, l, c, ctm, dt.year, (h+l+c)/3.0, v))
    return bars

def run(bars, p, slip=0.0):
    W=p["srHalfWidth"]; RIDE=p["ride"]; ZONE=p["zone"]; TP=p["tp"]; MAXSL=p["maxStop"]
    MAXSPREAD=p["maxSpread"]; SPREADON=p["enableSpread"]; CD=p["cooldown"]
    SHORT=p.get("enableShort",False); SNEAR=p.get("shortNear",5.0)
    STP=p.get("shortTp",60.0); SSL=p.get("shortSl",30.0)
    highs=[b[2] for b in bars]; lows=[b[3] for b in bars]; n=len(bars)
    lastFL=lastFH=None
    inpos=False; side=0; entry=exL=exH=None; pending=0; esp=None; ey=None; cd=0
    trades=[]  # (pnl, year, reason, dir)
    prevday=None; cumV=cumPV=cumPV2=0.0
    for bi in range(n):
        dt,o,h,l,c,ctm,yr,hlc3,vol = bars[bi]
        # volume-weighted daily VWAP ±2σ (approx of ta.vwap)
        d=dt.date()
        if d!=prevday: cumV=cumPV=cumPV2=0.0; prevday=d
        wv=vol if vol>0 else 1.0
        cumV+=wv; cumPV+=hlc3*wv; cumPV2+=hlc3*hlc3*wv
        mean=cumPV/cumV; sd=max(0.0,cumPV2/cumV-mean*mean)**0.5; vup=mean+2*sd; formed=(2*sd)>=1.0
        if bi>=2*W:
            ct=bi-W; ch=highs[ct]
            if all(ch>x for x in highs[bi-2*W:ct]) and all(ch>x for x in highs[ct+1:bi+1]): lastFH=ch
            cl=lows[ct]
            if all(cl<x for x in lows[bi-2*W:ct]) and all(cl<x for x in lows[ct+1:bi+1]): lastFL=cl
        if pending and not inpos:
            entry=o; inpos=True; side=pending; ey=yr
            if side==1: exL=max(esp-ZONE, entry-MAXSL); exH=entry+TP      # long: stop below, tp above
            else:       exL=entry-STP; exH=entry+SSL                       # short: tp below, stop above
            pending=0
        exited=False
        if inpos:
            if 900<=ctm<960:
                pnl=(c-entry) if side==1 else (entry-c)
                trades.append((pnl, ey, 'EOD', side)); inpos=False; exited=True
            elif side==1:
                if l<=exL:  fill=o if o<exL else exL; trades.append((fill-entry-slip, ey,'ESC',1)); inpos=False; exited=True
                elif h>=exH: fill=o if o>exH else exH; trades.append((fill-entry-slip, ey,'TP',1)); inpos=False; exited=True
            else:  # short
                if h>=exH:  fill=o if o>exH else exH; trades.append((entry-fill-slip, ey,'SL',-1)); inpos=False; exited=True
                elif l<=exL: fill=o if o<exL else exL; trades.append((entry-fill-slip, ey,'TP',-1)); inpos=False; exited=True
        if exited: cd=CD
        elif not inpos and cd>0: cd-=1
        if not inpos and not pending and cd==0 and not blocked(ctm):
            long_ok=False
            if lastFL is not None and lastFH is not None:
                touch=(c>=lastFL-RIDE) and (c<=lastFL+RIDE); spread=lastFH-lastFL
                long_ok = lastFL<lastFH and touch and ((not SPREADON) or spread<=MAXSPREAD)
            short_ok = SHORT and formed and (h>=vup-SNEAR)
            if long_ok:
                pending=1; esp=lastFL
            elif short_ok:
                pending=-1
    return trades

def summary(tr, V=2.0, label=""):
    if not tr:
        print(f"{label}: no trades"); return
    n=len(tr); w=sum(1 for t in tr if t[0]>0); net=sum(t[0] for t in tr)
    gp=sum(t[0] for t in tr if t[0]>0); gl=-sum(t[0] for t in tr if t[0]<=0)
    pf=gp/gl if gl>0 else 9.99
    yrs=sorted(set(t[1] for t in tr))
    py=sum(1 for y in yrs if sum(t[0] for t in tr if t[1]==y)>0)
    print(f"\n{label}")
    print(f"  trades {n}  win% {100*w/n:.1f}  net ${net*V:+,.0f}  PF {pf:.2f}  +yrs {py}/{len(yrs)}")
    print(f"  {'yr':>5} {'n':>6} {'win%':>6} {'net$':>10} {'PF':>5}")
    for y in yrs:
        g=[t for t in tr if t[1]==y]; ww=sum(1 for t in g if t[0]>0)
        yn=sum(t[0] for t in g); ygp=sum(t[0] for t in g if t[0]>0); ygl=-sum(t[0] for t in g if t[0]<=0)
        print(f"  {y:>5} {len(g):>6} {100*ww/len(g):>6.1f} {yn*V:>+10,.0f} {(ygp/ygl if ygl>0 else 9.99):>5.2f}")

P = dict(srHalfWidth=10, ride=5.0, zone=25.0, tp=20.0, maxStop=30.0,
         maxSpread=75.0, enableSpread=True, cooldown=5)

if __name__=="__main__":
    slip=float(sys.argv[1]) if len(sys.argv)>1 else 0.0
    print(f"DATA={DATA}  |  TZ=America/Chicago (pytz, DST-aware)")
    print(f"blocks: LN-open(120-150) + preNY/NY(450-540) + EOD(900-960)  [lunch/ETH/Asia REMOVED]")
    print(f"params={P}  slip={slip}")
    bars=load(DATA)
    print(f"loaded {len(bars)} bars  {bars[0][0].date()} → {bars[-1][0].date()}")
    summary(run(bars,P,slip), label=f"5YR (slip={slip})")
