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

## 9. Return-to-open — the clean number

Of pierce days, price returns to TOUCH the 14:30 open at some point AFTER the pierce, until EOD (21:00):
- **All pierce days: 76%**
- resistance: 75% · support: 78%

(Earlier loose "70%" figures came from arbitrary window cutoffs. 76% is the correct all-days-after-pierce measure. Touch WITHIN the window before 15:00 is ~100% and useless — price starts at the open.)

**The catch (survivorship):** the 76% that return to the open are the WEAK days. On days that pull back to the open, the rest-of-day move to EOD is ~0 (mean −1.6, median +1.8). The ~24% that NEVER return are the strong RUNAWAY days that carry the directional drift. So "wait for pullback to open" as an entry systematically selects the flat days and skips the runaways.

## 10. Buy-at-open / hold-EOD drift (theoretical, entry-locked)

`EOD close − open`, in the pierce direction:
- **All resistance days: mean +44.8, median +60.5, 64% close up** (428 days).
- winners-only subset (closed above open): median +123.8 / mean +150.7 (272 days) — CONDITIONAL, do not use as a target.
- losers-only: median −83.2 / mean −139.9 (156 days).
- Blind buy-open/hold-EOD on ALL 1,289 days (no filter): 54% up, mean +4.7, median +17 → the resistance pierce filter is what lifts 54%→64% and +4.7→+44.8.

**Entry-locked:** the +44.8 assumes buying at the 14:30 open, but direction is only known AFTER the pierce (median min 2), by which point price has left the open (~33 pts up at the band). Buying the pullback to open → the flat ~0 days (§9). So the drift is real but hard to capture cleanly.

## 11. What separates RUNAWAY days from reverters (early, observable features)

Resistance-pierce days, n=428, baseline revert-to-open rate **74%** (~26% runaways). Lower revert rate in a bucket = flags runaways.

**SLOPE at pierce — WORKS (monotonic):**
| slope at pierce | revert rate |
|---|---|
| negative | 89% (fade) |
| 0–5 | 77% |
| 5–10 | 63% |
| 10–20 | 58% |
| 20+ | 33% (runaway) |
→ Steep up-slope at pierce ≈ doubles the runaway rate (26%→42%). Strong-momentum pierce = genuine trend; flat/negative slope = exhaustion spike that reverts.

**PIERCE SPEED — works INVERSELY (flags reverters, not runaways):**
| min to pierce | revert rate |
|---|---|
| <1 (fast/violent) | 88% |
| 10–30 (slow grind) | 64% |
→ Fast tag of +2σ = overreaction that snaps back. Use to find FADE candidates, not runaways.

**OVERSHOOT past band — USELESS:** no monotonic pattern (68–84%, noise). Drop it.

**Implication:** slope at pierce may route each day to the right trade — fade the low/negative-slope pierces (reversion-prone), continue/hold the high-slope pierces (runaway-prone). This is the natural split to test next.

---

## Key takeaways

1. **The reversion (return-to-open) is a fast intraday DIP, not a trend reversal** (§7): 60–64% close back on the pierced side. Fade with a target, don't hold-to-EOD blindly.
2. **The signal (pierce) is knowable early** (median min 2, §6) but **entry-locked** — you can't buy at the open, and waiting for the pullback selects the flat days (§9, §10).
3. **Slope at pierce separates runaways (steep) from reverters (flat/negative)** (§11) — the key filter.
4. Short side (support→short continuation) fights NQ upward drift and is fragile; long/bounce is the robust side.

## Open questions / next experiments
- Split by SLOPE at pierce: fade low-slope pierces (reversion), hold high-slope pierces (runaway). Does routing beat either pure approach?
- The one untested entry: buy immediately at the pierce/band (accept worse price), hold to EOD — keeps you in the 24% runaways.
- Support-side symmetry of §11 (slope/speed drivers computed for resistance only).
