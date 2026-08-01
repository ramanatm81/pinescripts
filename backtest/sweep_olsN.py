import slope_touch_fade_bt as m
from datetime import datetime, timezone, timedelta
import statistics

CT = timezone(timedelta(hours=-5))
b5 = m.load(m.FIVE_YR)

# fixed Pine settings; only win_len (OLS N) varies. init stop ON buf10, trail off.
FIXED = dict(run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)

N_VALUES = [30, 40, 50, 60, 70, 80, 90]

# per-trade year needs entry time; trade_loop doesn't tag it, so re-derive entry bars here by
# replaying the same signal->entry logic is heavy. Instead: bucket net by year using a lightweight
# re-run that records entry epoch. Simplest: monkeypatch is overkill -- reuse trade_loop but map each
# trade to a year via the ENTRY price+order is not unique. So: compute per-year by slicing bars by year
# and running detect/trade_loop per-year is WRONG (detector needs continuous history).
# Correct approach: run full detect once per N, run trade_loop once, then attribute each trade to a
# year using a parallel entry-bar tracker built from the signals (mirror the loop, no PnL).

def entry_years(bars, sig, **tcfg):
    long_sig, short_sig, fext_long, fext_short = sig
    ctmin=[b[0] for b in bars]; high=[b[2] for b in bars]; low=[b[3] for b in bars]
    close=[b[4] for b in bars]; epoch=[b[5] for b in bars]
    block_ny=tcfg['block_ny']; block_ln=tcfg['block_ln']
    n=len(bars); pos=0; entry_i=None; years=[]
    for i in range(n):
        cm=ctmin[i]; gap=i>0 and (epoch[i]-epoch[i-1])/60.0>60
        sflat=(900<=cm<960) or (block_ny and 510<=cm<540) or (block_ln and 120<=cm<150) or gap
        rev=False
        if pos>0 and short_sig[i] and not sflat:
            years.append(datetime.fromtimestamp(epoch[entry_i],CT).year)  # close
            pos=-1; entry_i=i; rev=True
        elif pos<0 and long_sig[i] and not sflat:
            years.append(datetime.fromtimestamp(epoch[entry_i],CT).year)
            pos=1; entry_i=i; rev=True
        if sflat and pos!=0:
            years.append(datetime.fromtimestamp(epoch[entry_i],CT).year); pos=0; entry_i=None
        if pos==0 and not sflat and not rev:
            if long_sig[i] and not short_sig[i]: pos=1; entry_i=i
            elif short_sig[i] and not long_sig[i]: pos=-1; entry_i=i
    if pos!=0: years.append(datetime.fromtimestamp(epoch[entry_i],CT).year)
    return years

print(f"{'N':>4} {'trades':>6} {'net':>8} {'PF':>5} {'win%':>5} {'median':>7} {'exTop10':>8} {'yrs+':>5}")
for N in N_VALUES:
    sig = m.detect(b5, win_len=N, **FIXED)
    trades = m.trade_loop(b5, sig, **TRADE)
    st = m.stats(trades)
    pts = [t[3] for t in trades]
    yrs = entry_years(b5, sig, **TRADE)
    # net per year, count years with positive net
    from collections import defaultdict
    byyear = defaultdict(float)
    for p, y in zip(pts, yrs[:len(pts)]):
        byyear[y] += p
    pos_years = sum(1 for v in byyear.values() if v > 0)
    tot_years = len(byyear)
    med = statistics.median(pts) if pts else 0
    extop = sum(pts) - sum(sorted(pts)[-10:])
    pf = "inf" if st['pf']==float('inf') else f"{st['pf']:.2f}"
    print(f"{N:>4} {st['n']:>6} {st['net']:>8.0f} {pf:>5} {st['wr']:>5.0f} {med:>7.1f} {extop:>8.0f} {pos_years}/{tot_years}", flush=True)
