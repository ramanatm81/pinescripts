# RTH-Open ±2σ Pierce — Statistical Findings

**Instrument:** MNQ, 5yr (2021–2026), 1-min bars.
**Window:** 14:30–15:00 London (= 08:30–09:00 CT, the US cash RTH open).
**Bands:** daily-anchored VWAP ±2σ, anchor = London chart day (resets London midnight).
**Definitions:**
- *Pierce (resistance):* a bar's HIGH ≥ +2σ during the window.
- *Pierce (support):* a bar's LOW ≤ −2σ during the window.
- *Open:* the open of the 14:30 bar.
- *EOD:* 21:00 London (= 15:00 CT).

Scratch backtests/queries: `backtest/cluster_breakdown_5yr.py` and inline python (this session).

---

## 1. Range of the 14:30–15:00 window

| | pts |
|---|---|
| median range (high−low) | **101.8** |
| mean | 114.2 |
| p90 | 192.2 |

The RTH open is ~5× the overnight 02:30–03:00 window (median ~20 pts). This is where the movement is.

## 2. How often each band is pierced (independent events)

Days = 1,289.

| Event | days | % |
|---|---|---|
| Crossed RESISTANCE (+2σ) ≥ once | 428 | **33%** |
| Crossed SUPPORT (−2σ) ≥ once | 361 | **28%** |
| resistance only | 381 | 30% |
| support only | 314 | 24% |
| both bands | 47 | 4% |
| **neither** | 547 | **42%** |

Resistance touched slightly more (mild upside skew). Both-in-same-open is rare (4%) — opens commit to one direction.

## 3. Move size on pierce days (within the window)

| | median | mean | p90 |
|---|---|---|---|
| resistance: open → high (up move) | 71.8 | 79.3 | 146.5 |
| support: open → low (down move) | 79.2 | 91.3 | 178.5 |

Support/down moves are bigger & fatter-tailed than resistance/up ("sell-offs run harder").

## 4. Full-DAY range on pierce days

| | median | mean | p90 |
|---|---|---|---|
| resistance-pierce days | 275.2 | 321.1 | 512.8 |
| support-pierce days | 279.5 | 330.9 | 583.8 |

The 30-min open window (~106 med) is only ~⅓ of the full day (~275 med). A pierce at the open is the opening leg of a big-range day.

## 5. Geometry of a pierce (per-day, reconciles exactly)

```
open ──33pts──> +2σ band (first cross) ──28pts──> high (extreme)
     open→band = 33 median          band→high = 28 median
     open→high = 72 median  (per-day open→band + band→high = open→high, error 0)
```

- **Overshoot past the band vs band-at-the-high:** median 13 (band chases price up).
- **Overshoot past band vs band-at-first-cross (your entry level):** median 28.

## 6. TIMING within the window (resistance days; min 0 = 14:30)

| event | median minute | mean |
|---|---|---|
| first band cross (potential entry) | **2** | 6.5 |
| session high (extreme) | **19** | 16.8 |
| minutes left after cross | 28 | 23.5 |

- Pierce is a **fast opening spike** (~min 2).
- High comes **~17 min later** — the "band→high" 28pts is a slow adverse grind, not instant.
- 76% of days: high comes AFTER the cross (price keeps running past a band-entry). Only 24% spike-and-done.

## 7. Reversion to open — the headline, and its trap

**Touched open at some point before EOD:**
- resistance days: **70%** (299/428)
- support days: **71%** (258/361)

**BUT — "touched" ≠ "closed past". EOD close still on the PIERCED side:**
- resistance: **64%** close still ABOVE open (272/428)
- support: **60%** close still BELOW open (215/361)

→ On the majority of pierce days the **pierce direction WINS by the close.** The reversion to open is a **fast intraday DIP, not a trend reversal.** Price kisses the open, then resumes.

## 8. Position at 15:00 — the selection trap

Of pierce days:
- **85%** are already back INSIDE the band by 15:00 (632/742). Reversion is fast, mostly within the window.
- **15%** are still beyond the band at 15:00 (110/742).

**Revert-to-open-by-EOD rate, split by 15:00 position:**
| group | revert rate |
|---|---|
| ALL pierce days | 70% |
| already back inside by 15:00 | **75%** |
| still beyond band at 15:00 | **42%** ← the trap |

"Still extended at 15:00" is a **momentum-persistence (trend) signal**, NOT a coiled spring. The quick reverters already turned before 15:00; what's left standing keeps going.

---

## Backtest results so far

**A. Fade at the band, intrabar, target = open, EOD flat, buffer 0, SL 30, 1pt slip:**
**+3,790 pts / 5yr, 742 trades, 57% win, 6/6 positive years. LONG +1,464 / SHORT +2,327.**
- Buffer HURTS (0 best; 15/30/50 progressively worse — waiting for overshoot = fewer, worse-priced entries).
- Tighter SL better on PnL (30 > 50 > 70). Fade → tight stop.
- BOTH directions profitable; short (fade resistance) is the bigger winner. Unusual vs prior strategies where short lost.
- This works because it enters EARLY (median min 2) and catches the fast 85% reverter majority; the profit target grabs the fleeting dip before the day resumes.

**B. Enter at 15:00 IF still beyond band, target = open, EOD flat:**
**LOSES at every SL (−477 to −1,380), only 119 trades, 2/6 years.**
- Selection trap (§8): filters for the 42%-revert trend days, discards the 75%-revert quick reverters.
- Target is huge (~118 pts) because entry is late/extended. Do NOT use this filter.

---

## Key takeaways for next steps

1. **The edge is intraday mean-reversion WITH a profit target — NOT hold-to-EOD** (§7: 60–64% close on the pierced side).
2. **Enter early (at/near the band, intrabar), not at 15:00** (§6 timing, §8 selection trap).
3. **Buffer beyond band hurts; tight SL helps** (backtest A).
4. Open-conditions to still verify on the winning version: honest fills, per-year robustness, target choice (open vs VWAP vs partial), then add trail.

## Open questions / next experiments
- Best target-based exit on the intrabar fade: open vs VWAP mean vs partial-scale.
- Honest-fill audit of backtest A (open-touch exit could be optimistic on gaps).
- Does a 15:00 entry work if we FLIP the filter — fade days already back INSIDE the band (75% reverters)?
- Add trailing stop (user wants it later) once the base target-exit is locked.
