"""Weekly walk-forward adaptive-N on the FAST numba engine.

For each week t, pick N(t) from ONLY the trailing 4 weeks (out-of-sample), trade week t with that N.
Predictors: OU half-life, vol-rule, regime-label, vs fixed-90 baseline. Concatenated OOS, per-year +
tail gate. Precompute each candidate N's signals ONCE (JIT), then a single JIT trade loop reads a
per-bar 'which N to use' array. Runs in seconds.
"""
import numpy as np, math, statistics, time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from numba import njit
import slope_touch_fade_bt as m
from fast_detect import _detect_core, _pivots
from fast_sim import fast_bars

CT = timezone(timedelta(hours=-5))
DET = dict(run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)
N_GRID = [40, 60, 90, 130]
LOOKBACK = 4

b5 = m.load(m.FIVE_YR)
A = fast_bars(b5)
n = len(b5)
close = A["c"]; epoch = A["ep"]

# week key per bar
def wkey(ep):
    d = datetime.fromtimestamp(ep, CT); iso = d.isocalendar(); return iso[0] * 100 + iso[1]
bar_week = np.array([wkey(e) for e in epoch])
weeks = sorted(set(bar_week.tolist()))
week_bars = defaultdict(list)
for i in range(n):
    week_bars[int(bar_week[i])].append(i)
week_idx = {w: k for k, w in enumerate(weeks)}
# map each bar to its week's ordinal (for the JIT loop)
bar_wordinal = np.array([week_idx[int(bar_week[i])] for i in range(n)], np.int32)

# precompute signals for each candidate N once
res, supp = _pivots(A["h"], A["l"], DET["sr_half"])
sig_by_N = {}
print("precomputing detect() per candidate N (fast) ...", flush=True)
t0 = time.time()
for N in N_GRID:
    ls, ss, fl, fs, la, sa = _detect_core(A["h"], A["l"], A["c"], A["ep"], res, supp,
                                          N, DET["run_min"], DET["min_r2"], DET["pullback"], DET["break_tol"])
    sig_by_N[N] = (ls, ss, fl, fs)
print(f"  {len(N_GRID)} detects in {time.time()-t0:.1f}s", flush=True)

# stack signals: [gridpos][bar]
GI = {N: k for k, N in enumerate(N_GRID)}
LS = np.stack([sig_by_N[N][0] for N in N_GRID])
SS = np.stack([sig_by_N[N][1] for N in N_GRID])
FL = np.stack([sig_by_N[N][2] for N in N_GRID])
FS = np.stack([sig_by_N[N][3] for N in N_GRID])


@njit(cache=True)
def _wf_loop(ctmin, high, low, close, epoch, LS, SS, FL, FS, bar_wordinal, week_gridpos,
            block_ny, block_ln, enable_init, stop_buf):
    """Trade loop where the ACTIVE N (grid position) on each bar is week_gridpos[bar_wordinal[i]].
    Signals read from the stacked arrays at that grid row. Returns arrays of trade pts + entry week."""
    n = close.shape[0]
    pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan
    out_pts = np.empty(n); out_wk = np.empty(n, np.int32); ntr = 0
    for i in range(n):
        gp = week_gridpos[bar_wordinal[i]]     # which N (grid row) is active this week
        ls = LS[gp, i]; ss = SS[gp, i]; fl = FL[gp, i]; fs = FS[gp, i]
        cm = ctmin[i]
        gap = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        sflat = (900 <= cm < 960) or (block_ny and 510 <= cm < 540) or (block_ln and 120 <= cm < 150) or gap
        closed = False; rev = False
        if pos > 0 and ss and not sflat:
            out_pts[ntr] = close[i] - entry_px; out_wk[ntr] = bar_wordinal[i]; ntr += 1
            pos = -1; entry_px = close[i]; best = low[i]
            init_stop = (fs + stop_buf) if not np.isnan(fs) else np.nan; rev = True
        elif pos < 0 and ls and not sflat:
            out_pts[ntr] = entry_px - close[i]; out_wk[ntr] = bar_wordinal[i]; ntr += 1
            pos = 1; entry_px = close[i]; best = high[i]
            init_stop = (fl - stop_buf) if not np.isnan(fl) else np.nan; rev = True
        if (not rev) and pos > 0 and enable_init:
            if high[i] > best: best = high[i]
            sl = init_stop
            if (not np.isnan(sl)) and low[i] <= sl:
                out_pts[ntr] = sl - entry_px; out_wk[ntr] = bar_wordinal[i]; ntr += 1
                pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        elif (not rev) and pos < 0 and enable_init:
            if low[i] < best: best = low[i]
            sl = init_stop
            if (not np.isnan(sl)) and high[i] >= sl:
                out_pts[ntr] = entry_px - sl; out_wk[ntr] = bar_wordinal[i]; ntr += 1
                pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        if sflat and pos != 0:
            out_pts[ntr] = (close[i] - entry_px) if pos > 0 else (entry_px - close[i]); out_wk[ntr] = bar_wordinal[i]; ntr += 1
            pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        if pos == 0 and not sflat and not closed and not rev:
            if ls and not ss:
                pos = 1; entry_px = close[i]; best = high[i]
                init_stop = (fl - stop_buf) if not np.isnan(fl) else np.nan
            elif ss and not ls:
                pos = -1; entry_px = close[i]; best = low[i]
                init_stop = (fs + stop_buf) if not np.isnan(fs) else np.nan
    if pos != 0:
        out_pts[ntr] = (close[n - 1] - entry_px) if pos > 0 else (entry_px - close[n - 1]); out_wk[ntr] = bar_wordinal[n - 1]; ntr += 1
    return out_pts[:ntr], out_wk[:ntr]


def run_predictor(week_gridpos):
    pts, _ = _wf_loop(A["ctmin"], A["h"], A["l"], A["c"], A["ep"], LS, SS, FL, FS,
                      bar_wordinal, week_gridpos, TRADE["block_ny"], TRADE["block_ln"],
                      TRADE["enable_init"], TRADE["stop_buf"])
    return pts

# ---- predictors: return grid-position per week ----
def nearest_gp(x): return GI[min(N_GRID, key=lambda g: abs(g - x))]

def gp_fixed(N):
    return np.full(len(weeks), GI[N], np.int32)

def gp_ou():
    out = np.full(len(weeks), GI[90], np.int32)
    for wi in range(LOOKBACK, len(weeks)):
        trail = []
        for j in range(wi - LOOKBACK, wi): trail += week_bars[weeks[j]]
        c = close[np.array(trail)]
        if len(c) < 50: continue
        lag = c[:-1]; delta = np.diff(c)
        mlag = lag.mean(); var = ((lag - mlag) ** 2).sum()
        if var <= 0: continue
        cov = ((lag - mlag) * (delta - delta.mean())).sum()
        theta = -cov / var
        if theta <= 1e-9: out[wi] = GI[max(N_GRID)]; continue
        out[wi] = nearest_gp(math.log(2) / theta)
    return out

def gp_vol():
    vols = []
    for wi in range(LOOKBACK, len(weeks)):
        trail = []
        for j in range(wi - LOOKBACK, wi): trail += week_bars[weeks[j]]
        c = close[np.array(trail)]
        vols.append(float(np.diff(c).std()) if len(c) > 2 else 0.0)
    lo, hi = statistics.quantiles(vols, n=3) if len(vols) >= 3 else (0, 0)
    out = np.full(len(weeks), GI[90], np.int32)
    for k, wi in enumerate(range(LOOKBACK, len(weeks))):
        v = vols[k]
        out[wi] = GI[min(N_GRID)] if v >= hi else (GI[max(N_GRID)] if v <= lo else GI[90])
    return out

@njit(cache=True)
def _net_one_N(ctmin, high, low, close, epoch, ls_a, ss_a, fl_a, fs_a, bar_wordinal,
               wk_lo, wk_hi, block_ny, block_ln, enable_init, stop_buf):
    """Net points for ONE N (its signal arrays), counting only trades whose ENTRY week ordinal is in
    [wk_lo, wk_hi). Full sequential loop over all bars (position carries), but a trade's pts count
    toward the total only if entered in-window. Used to score N on the trailing 3 weeks."""
    n = close.shape[0]
    pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; entry_w = -1
    net = 0.0
    for i in range(n):
        w = bar_wordinal[i]
        cm = ctmin[i]
        gap = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        sflat = (900 <= cm < 960) or (block_ny and 510 <= cm < 540) or (block_ln and 120 <= cm < 150) or gap
        closed = False; rev = False
        if pos > 0 and ss_a[i] and not sflat:
            if wk_lo <= entry_w < wk_hi: net += close[i] - entry_px
            pos = -1; entry_px = close[i]; best = low[i]; entry_w = w
            init_stop = (fs_a[i] + stop_buf) if not np.isnan(fs_a[i]) else np.nan; rev = True
        elif pos < 0 and ls_a[i] and not sflat:
            if wk_lo <= entry_w < wk_hi: net += entry_px - close[i]
            pos = 1; entry_px = close[i]; best = high[i]; entry_w = w
            init_stop = (fl_a[i] - stop_buf) if not np.isnan(fl_a[i]) else np.nan; rev = True
        if (not rev) and pos > 0 and enable_init:
            if high[i] > best: best = high[i]
            sl = init_stop
            if (not np.isnan(sl)) and low[i] <= sl:
                if wk_lo <= entry_w < wk_hi: net += sl - entry_px
                pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        elif (not rev) and pos < 0 and enable_init:
            if low[i] < best: best = low[i]
            sl = init_stop
            if (not np.isnan(sl)) and high[i] >= sl:
                if wk_lo <= entry_w < wk_hi: net += entry_px - sl
                pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        if sflat and pos != 0:
            if wk_lo <= entry_w < wk_hi: net += (close[i] - entry_px) if pos > 0 else (entry_px - close[i])
            pos = 0; entry_px = np.nan; init_stop = np.nan; best = np.nan; closed = True
        if pos == 0 and not sflat and not closed and not rev:
            if ls_a[i] and not ss_a[i]:
                pos = 1; entry_px = close[i]; best = high[i]; entry_w = w
                init_stop = (fl_a[i] - stop_buf) if not np.isnan(fl_a[i]) else np.nan
            elif ss_a[i] and not ls_a[i]:
                pos = -1; entry_px = close[i]; best = low[i]; entry_w = w
                init_stop = (fs_a[i] + stop_buf) if not np.isnan(fs_a[i]) else np.nan
    return net


def gp_trailing_best(lookback):
    """Each week wi: pick the N with highest NET over weeks [wi-lookback, wi); use it for week wi."""
    out = np.full(len(weeks), GI[90], np.int32)
    for wi in range(lookback, len(weeks)):
        best_net = -1e18; best_gp = GI[90]
        for N in N_GRID:
            ls, ss, fl, fs = sig_by_N[N]
            net = _net_one_N(A["ctmin"], A["h"], A["l"], A["c"], A["ep"], ls, ss, fl, fs,
                             bar_wordinal, wi - lookback, wi,
                             TRADE["block_ny"], TRADE["block_ln"], TRADE["enable_init"], TRADE["stop_buf"])
            if net > best_net:
                best_net = net; best_gp = GI[N]
        out[wi] = best_gp
    return out


def report(label, pts):
    if len(pts) == 0: print(f"{label:>14}: (none)"); return
    net = pts.sum(); wins = int((pts > 0).sum())
    med = float(np.median(pts)); extop = net - np.sort(pts)[-10:].sum()
    # per-year
    print(f"{label:>14}: n={len(pts):>4} net={net:>7.0f} med={med:>6.1f} win%={100*wins/len(pts):>3.0f} exTop10={extop:>7.0f}")

print("\n=== weekly walk-forward, concatenated OOS ===", flush=True)
t0 = time.time()
report("fixed-90", run_predictor(gp_fixed(90)))
report("OU-halflife", run_predictor(gp_ou()))
report("vol-rule", run_predictor(gp_vol()))
gp_tb3 = gp_trailing_best(3)   # trailing-best-N by net, 3-week lookback -> next week
report("trailBest-3wk", run_predictor(gp_tb3))
print(f"  (ran in {time.time()-t0:.1f}s)")
for name, gp in [("OU", gp_ou()), ("vol", gp_vol()), ("trailBest3", gp_tb3)]:
    dist = defaultdict(int)
    for v in gp: dist[N_GRID[v]] += 1
    print(f"  {name} N-distribution: {dict(sorted(dist.items()))}")
