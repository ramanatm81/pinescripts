"""Weekly walk-forward adaptive-N for slope_touch_fade.

For each week t: pick N(t) using ONLY the trailing 4 weeks [t-4, t-1] (strictly out-of-sample),
trade week t with that N. Concatenate all OOS weeks -> honest adaptive-N P&L. Compare predictors:
  - OU half-life : N = ln(2)/theta from AR(1) fit on trailing closes (clamped to N grid)
  - vol-rule     : trailing realized vol -> N (high vol -> short N), monotone
  - fixed-90     : baseline
Detector is precomputed once per candidate N over the full 5yr (needs pre-week warmup); each week
reads signals from the matching N's arrays. Trades are attributed to the week of their ENTRY bar.
"""
import slope_touch_fade_bt as m
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import math, statistics, time

CT = timezone(timedelta(hours=-5))
b5 = m.load(m.FIVE_YR)
FIXED = dict(run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)
N_GRID = [40, 60, 90, 130]          # candidate N values (precompute detect for each)
LOOKBACK_WEEKS = 4

close = [b[4] for b in b5]; epoch = [b[5] for b in b5]
n = len(b5)

# ISO week key per bar
def wkey(ep):
    d = datetime.fromtimestamp(ep, CT)
    iso = d.isocalendar()
    return iso[0] * 100 + iso[1]
bar_week = [wkey(e) for e in epoch]
weeks = sorted(set(bar_week))
week_bars = defaultdict(list)
for i in range(n):
    week_bars[bar_week[i]].append(i)

print("precomputing detect() for each candidate N (slow) ...", flush=True)
t0 = time.time()
sig_by_N = {}
for N in N_GRID:
    sig_by_N[N] = m.detect(b5, win_len=N, **FIXED)
    print(f"  N={N} done ({time.time()-t0:.0f}s)", flush=True)

# For a given N and a set of allowed ENTRY weeks, run the trade loop but only OPEN when the entry
# bar's week is in `open_weeks`. (Trades still exit normally.) Returns list of (entry_week, pts).
def run_weeks(N, open_weeks):
    long_sig, short_sig, fext_l, fext_s = sig_by_N[N]
    ctmin=[b[0] for b in b5]; high=[b[2] for b in b5]; low=[b[3] for b in b5]
    pos=0; entry_px=None; entry_i=None; out=[]
    def close_tr(d,px):
        pts=(px-entry_px) if d>0 else (entry_px-px); out.append((bar_week[entry_i], pts))
    for i in range(n):
        cm=ctmin[i]; gap=i>0 and (epoch[i]-epoch[i-1])/60.0>60
        sflat=(900<=cm<960) or (510<=cm<540) or (120<=cm<150) or gap
        ok = bar_week[i] in open_weeks
        rev=False
        if pos>0 and short_sig[i] and not sflat:
            close_tr(1,close[i])
            if ok: pos=-1; entry_px=close[i]; entry_i=i; rev=True
            else: pos=0; entry_px=None; entry_i=None
        elif pos<0 and long_sig[i] and not sflat:
            close_tr(-1,close[i])
            if ok: pos=1; entry_px=close[i]; entry_i=i; rev=True
            else: pos=0; entry_px=None; entry_i=None
        if sflat and pos!=0:
            close_tr(pos,close[i]); pos=0; entry_px=None; entry_i=None
        if pos==0 and not sflat and not rev and ok:
            if long_sig[i] and not short_sig[i]: pos=1; entry_px=close[i]; entry_i=i
            elif short_sig[i] and not long_sig[i]: pos=-1; entry_px=close[i]; entry_i=i
    if pos!=0: close_tr(pos, close[-1])
    return out

# --- predictors: from trailing 4 weeks of closes, return an N from N_GRID ---
def nearest_N(x):
    return min(N_GRID, key=lambda g: abs(g - x))

def ou_halflife_N(bars_idx):
    c = [close[i] for i in bars_idx]
    if len(c) < 50: return 90
    lag = c[:-1]; delta = [c[k+1]-c[k] for k in range(len(c)-1)]
    mlag = sum(lag)/len(lag)
    var = sum((x-mlag)**2 for x in lag)
    if var <= 0: return 90
    cov = sum((lag[k]-mlag)*(delta[k]-(sum(delta)/len(delta))) for k in range(len(lag)))
    theta = -cov/var                       # AR(1): delta = -theta*(p-mu); theta>0 = mean-reverting
    if theta <= 1e-9: return max(N_GRID)   # no reversion -> long window
    hl = math.log(2)/theta
    return nearest_N(hl)

# vol-rule: rank trailing realized vol across the whole history into terciles -> short/mid/long N
def realized_vol(bars_idx):
    c=[close[i] for i in bars_idx]
    if len(c)<10: return 0.0
    r=[c[k+1]-c[k] for k in range(len(c)-1)]
    return statistics.pstdev(r)

# precompute per-week trailing-vol to set tercile thresholds (uses only past, but thresholds are
# global -> mild lookahead on calibration only; acceptable for a first pass, noted honestly)
def build_week_N(predictor):
    week_N = {}
    for wi, wk in enumerate(weeks):
        if wi < LOOKBACK_WEEKS:
            week_N[wk] = 90; continue
        trail = []
        for j in range(wi-LOOKBACK_WEEKS, wi):
            trail += week_bars[weeks[j]]
        week_N[wk] = predictor(trail)
    return week_N

def vol_predictor_factory():
    # global tercile thresholds from all 4-week trailing vols
    vols=[]
    for wi in range(LOOKBACK_WEEKS, len(weeks)):
        trail=[]
        for j in range(wi-LOOKBACK_WEEKS, wi): trail+=week_bars[weeks[j]]
        vols.append(realized_vol(trail))
    lo,hi = statistics.quantiles(vols, n=3) if len(vols)>=3 else (0,0)
    def pred(trail):
        v=realized_vol(trail)
        if v>=hi: return min(N_GRID)     # high vol -> short N
        if v<=lo: return max(N_GRID)     # low vol -> long N
        return 90
    return pred

# --- run each predictor: build week->N, then group weeks by N and run each group ---
def concat_oos(week_N):
    byN=defaultdict(set)
    for wk,N in week_N.items(): byN[N].add(wk)
    allpts=[]
    for N,wks in byN.items():
        allpts += [p for _,p in run_weeks(N, wks)]
    return allpts

def report(label, pts):
    if not pts: print(f"{label:>16}: (none)"); return
    net=sum(pts); wins=sum(1 for p in pts if p>0)
    med=statistics.median(pts); extop=net-sum(sorted(pts)[-10:])
    print(f"{label:>16}: n={len(pts):>4} net={net:>7.0f} PF~ med={med:>6.1f} win%={100*wins/len(pts):>3.0f} exTop10={extop:>7.0f}")

print("\n=== weekly walk-forward (4wk lookback), concatenated OOS ===", flush=True)
# baseline: fixed 90 every week
report("fixed-90", [p for _,p in run_weeks(90, set(weeks))])
report("OU-halflife", concat_oos(build_week_N(ou_halflife_N)))
report("vol-rule", concat_oos(build_week_N(vol_predictor_factory())))

# show the N-distribution each predictor chose
for name,pred in [("OU", ou_halflife_N), ("vol", vol_predictor_factory())]:
    wN=build_week_N(pred); dist=defaultdict(int)
    for v in wN.values(): dist[v]+=1
    print(f"  {name} N-distribution: {dict(sorted(dist.items()))}")
