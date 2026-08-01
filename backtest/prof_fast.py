import slope_touch_fade_bt as m
from fast_detect import _detect_core, _pivots
import numpy as np, time
b5 = m.load(m.FIVE_YR); n = len(b5)
t = time.time()
high = np.array([b[2] for b in b5]); low = np.array([b[3] for b in b5])
close = np.array([b[4] for b in b5]); epoch = np.array([b[5] for b in b5])
print(f"array build (one-time): {time.time()-t:.2f}s")
res, supp = _pivots(high, low, 10)
t = time.time(); res, supp = _pivots(high, low, 10); print(f"pivots: {time.time()-t:.2f}s")
_detect_core(high, low, close, epoch, res, supp, 90, 100.0, 0.75, 70.0, 5.0)
t = time.time()
_detect_core(high, low, close, epoch, res, supp, 90, 100.0, 0.75, 70.0, 5.0)
print(f"detect core (pure JIT, no conversion): {time.time()-t:.2f}s")
