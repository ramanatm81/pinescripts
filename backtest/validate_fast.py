import slope_touch_fade_bt as m
from fast_detect import detect_fast
import time

b5 = m.load(m.FIVE_YR)
CFG = dict(win_len=90, run_min=100.0, min_r2=0.75, pullback=70.0, break_tol=5.0, sr_half=10)
TRADE = dict(block_ny=True, block_ln=True, enable_trail=False, enable_init=True, stop_buf=10.0)

print("pure-Python detect() ...", flush=True)
t0 = time.time(); sig_slow = m.detect(b5, **CFG); t_slow = time.time() - t0
print(f"  {t_slow:.1f}s", flush=True)

print("numba detect_fast() (incl. first-call compile) ...", flush=True)
t0 = time.time(); sig_fast = detect_fast(b5, **CFG); t_fast1 = time.time() - t0
t0 = time.time(); sig_fast = detect_fast(b5, **CFG); t_fast2 = time.time() - t0
print(f"  compile+run {t_fast1:.1f}s, cached run {t_fast2:.2f}s", flush=True)

# exact-match the signal arrays
ls_s, ss_s, fl_s, fs_s = sig_slow
ls_f, ss_f, fl_f, fs_f = sig_fast
def diff_bool(a, b): return sum(1 for x, y in zip(a, b) if x != y)
def diff_opt(a, b):
    d = 0
    for x, y in zip(a, b):
        if (x is None) != (y is None): d += 1
        elif x is not None and abs(x - y) > 1e-6: d += 1
    return d
print(f"\nsignal diffs: long_sig={diff_bool(ls_s,ls_f)} short_sig={diff_bool(ss_s,ss_f)} "
      f"fext_long={diff_opt(fl_s,fl_f)} fext_short={diff_opt(fs_s,fs_f)}")

# and the final trade stats must match
st_s = m.stats(m.trade_loop(b5, sig_slow, **TRADE))
st_f = m.stats(m.trade_loop(b5, sig_fast, **TRADE))
print(f"slow  trades={st_s['n']} net={st_s['net']:.1f} PF={st_s['pf']:.2f}")
print(f"fast  trades={st_f['n']} net={st_f['net']:.1f} PF={st_f['pf']:.2f}")
match = (st_s['n'] == st_f['n'] and abs(st_s['net'] - st_f['net']) < 1e-6)
print(f"\nMATCH: {'YES' if match else 'NO'}   speedup: {t_slow/t_fast2:.0f}x (cached)")
