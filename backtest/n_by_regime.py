import slope_touch_fade_bt as m
from regime import regime_per_bar
from collections import defaultdict
import statistics, time

b5 = m.load(m.FIVE_YR)
FIXED = dict(run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)

t0 = time.time()
reg = regime_per_bar(b5)   # +1 dir-up, -1 dir-down, 0 mean-reversion, per 1m bar
print(f"regime computed in {time.time()-t0:.0f}s")
frac_dir = sum(1 for r in reg if r != 0) / len(reg)
print(f"bars: directional {100*frac_dir:.0f}%  mean-reversion {100*(1-frac_dir):.0f}%\n")

# rebuild trade entry bars for a given N so we can tag each trade by its ENTRY regime.
def trades_with_entry_bar(bars, sig):
    long_sig, short_sig, fext_l, fext_s = sig[:4]
    ctmin=[b[0] for b in bars]; high=[b[2] for b in bars]; low=[b[3] for b in bars]
    close=[b[4] for b in bars]; epoch=[b[5] for b in bars]
    n=len(bars); pos=0; entry_px=None; entry_i=None; out=[]
    def close_tr(d,px,ei):
        pts=(px-entry_px) if d>0 else (entry_px-px); out.append((ei,pts))
    for i in range(n):
        cm=ctmin[i]; gap=i>0 and (epoch[i]-epoch[i-1])/60.0>60
        sflat=(900<=cm<960) or (510<=cm<540) or (120<=cm<150) or gap
        rev=False
        if pos>0 and short_sig[i] and not sflat:
            close_tr(1,close[i],entry_i); pos=-1; entry_px=close[i]; entry_i=i; rev=True
        elif pos<0 and long_sig[i] and not sflat:
            close_tr(-1,close[i],entry_i); pos=1; entry_px=close[i]; entry_i=i; rev=True
        if sflat and pos!=0:
            close_tr(pos,close[i],entry_i); pos=0; entry_px=None; entry_i=None
        if pos==0 and not sflat and not rev:
            if long_sig[i] and not short_sig[i]: pos=1; entry_px=close[i]; entry_i=i
            elif short_sig[i] and not long_sig[i]: pos=-1; entry_px=close[i]; entry_i=i
    if pos!=0: close_tr(pos,close[-1],entry_i)
    return out   # list of (entry_bar_index, pts)

def bucket(name, trs):
    if not trs: print(f"    {name:>14}: (none)"); return
    pts=[p for _,p in trs]; net=sum(pts); wins=sum(1 for p in pts if p>0)
    med=statistics.median(pts); extop=net-sum(sorted(pts)[-10:])
    print(f"    {name:>14}: n={len(trs):>4} net={net:>7.0f} med={med:>6.1f} win%={100*wins/len(trs):>3.0f} exTop10={extop:>7.0f}")

print(f"{'N':>4}  per-regime split (MR = mean-reversion, DIR = directional):")
for N in [30,40,50,60,90,150]:
    sig=m.detect(b5,win_len=N,**FIXED)
    trs=trades_with_entry_bar(b5,sig)
    mr=[(ei,p) for ei,p in trs if reg[ei]==0]
    dr=[(ei,p) for ei,p in trs if reg[ei]!=0]
    print(f"  N={N}:")
    bucket("ALL", trs); bucket("mean-revert", mr); bucket("directional", dr)
