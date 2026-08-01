import slope_touch_fade_bt as m
from fast_sim import fast_bars, sim
import time

b5 = m.load(m.FIVE_YR)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)

# reference (pure python) at a few configs
print("building arrays once ...", flush=True)
t0 = time.time(); A = fast_bars(b5); print(f"  {time.time()-t0:.2f}s", flush=True)

print("\n=== correctness: fast sim vs pure-python port ===", flush=True)
for N in [90, 150]:
    det = dict(win_len=N, run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)
    ref = m.stats(m.trade_loop(b5, m.detect(b5, **det), **TRADE))
    fast = sim(A, **det, **TRADE)
    ok = ref['n'] == fast['n'] and abs(ref['net'] - fast['net']) < 1e-6
    print(f"  N={N}: port n={ref['n']} net={ref['net']:.1f} | fast n={fast['n']} net={fast['net']:.1f} "
          f"| {'MATCH' if ok else 'MISMATCH'}", flush=True)

print("\n=== speed: full OLS-N sweep, all-numpy ===", flush=True)
N_VALUES = [30, 40, 50, 60, 70, 80, 90, 110, 130, 150, 170, 190, 220, 250, 300]
t0 = time.time()
for N in N_VALUES:
    s = sim(A, win_len=N, **TRADE)
print(f"  {len(N_VALUES)} configs in {time.time()-t0:.1f}s  ({(time.time()-t0)/len(N_VALUES):.2f}s/config)")
