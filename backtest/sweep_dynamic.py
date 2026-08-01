import slope_touch_fade_bt as m
from dynamic_n import detect_dynamic
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import statistics, time, sys

CT = timezone(timedelta(hours=-5))
b5 = m.load(m.FIVE_YR)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)
FIXED = dict(run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)


def entry_years(bars, sig):
    ctmin=[b[0] for b in bars]; epoch=[b[5] for b in bars]
    long_sig, short_sig, fext_l, fext_s = sig[:4]
    n=len(bars); pos=0; entry_i=None; years=[]
    for i in range(n):
        cm=ctmin[i]; gap=i>0 and (epoch[i]-epoch[i-1])/60.0>60
        sflat=(900<=cm<960) or (510<=cm<540) or (120<=cm<150) or gap
        rev=False
        if pos>0 and short_sig[i] and not sflat:
            years.append(datetime.fromtimestamp(epoch[entry_i],CT).year); pos=-1; entry_i=i; rev=True
        elif pos<0 and long_sig[i] and not sflat:
            years.append(datetime.fromtimestamp(epoch[entry_i],CT).year); pos=1; entry_i=i; rev=True
        if sflat and pos!=0:
            years.append(datetime.fromtimestamp(epoch[entry_i],CT).year); pos=0; entry_i=None
        if pos==0 and not sflat and not rev:
            if long_sig[i] and not short_sig[i]: pos=1; entry_i=i
            elif short_sig[i] and not long_sig[i]: pos=-1; entry_i=i
    if pos!=0: years.append(datetime.fromtimestamp(epoch[entry_i],CT).year)
    return years


CONFIGS = [
    ("dyn 60-240/10", dict(win_min=60, win_max=240, win_step=10)),
    ("dyn 60-150/10", dict(win_min=60, win_max=150, win_step=10)),
    ("dyn 80-120/10", dict(win_min=80, win_max=120, win_step=10)),
]
print(f"{'config':>16} {'trades':>6} {'net':>8} {'PF':>5} {'win%':>5} {'median':>7} {'exTop10':>8} {'yrs+':>5} {'sec':>5}")
for name, wcfg in CONFIGS:
    t0=time.time()
    sig = detect_dynamic(b5, **wcfg, **FIXED)
    trades = m.trade_loop(b5, sig, **TRADE)
    st = m.stats(trades); pts=[t[3] for t in trades]
    yrs = entry_years(b5, sig)
    by=defaultdict(float)
    for p,y in zip(pts,yrs[:len(pts)]): by[y]+=p
    posy=sum(1 for v in by.values() if v>0)
    med=statistics.median(pts) if pts else 0
    extop=sum(pts)-sum(sorted(pts)[-10:])
    pf="inf" if st['pf']==float('inf') else f"{st['pf']:.2f}"
    print(f"{name:>16} {st['n']:>6} {st['net']:>8.0f} {pf:>5} {st['wr']:>5.0f} {med:>7.1f} {extop:>8.0f} {posy}/{len(by)} {time.time()-t0:>5.0f}", flush=True)
