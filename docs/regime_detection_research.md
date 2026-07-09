# Intraday Regime Detection for NQ — Research Notes

**Question:** How to classify 1-minute NQ (Nasdaq-100 futures) into **directional (trending)**
vs **mean-reverting (range/chop)** regimes, computably in TradingView Pine Script, to
decide which strategy/account to run.

**Sources:** arxiv.org + practitioner references (StockCharts, Lo-MacKinlay notes).
Cross-checked against this repo's own backtests (see `fade-filters-hurt` learning).

---

## TL;DR — what to actually use (UPDATED: multi-timeframe)

**The single most important decision is TIMEFRAME, not method.** On 1-min, index
futures are statistically indistinguishable from a random walk (Hurst ≈ 0.5) — the
regime is *undetectable*. Detectability rises monotonically with bar size; the trending
regime lives ~1 hour to months. **So JUDGE the regime on a HIGHER timeframe (1-hour),
and EXECUTE on your 1-5min ladder.**

Recommended build (all Pine-computable, causal, no matrices/EM/ML):

1. **Rolling regression R² + slope (on the 1h bar)** — the current-state axis.
   `r2 = ta.correlation(close, bar_index, N)^2`, direction = sign of `ta.linreg` slope.
   R² has a *calibrated significance table* (N=20 → R²>0.20 = real trend) that the
   Efficiency Ratio lacks — and ER's textbook direction backtests *inverted*. Use R².
2. **Volatility Switch (McEwan/LazyBear, on the 1h bar)** — a second orthogonal vote.
   Normalized vol; falling vol → trend mode, rising vol → mean-reversion mode (thr 0.5).
3. **CUSUM on standardized 1h returns** — the CHANGE-POINT timer ("when did it change").
   2 scalar accumulators, slack `k` + interval `h`; tunable lag/false-alarm. Lighter and
   earlier than N-bar confirmation.

Combine: label = f(R²/slope, vol-switch) on the confirmed prior 1h bar; CUSUM flag =
change-point; stabilize with N-bar debounce + min-dwell. **MTF safety:** read the HTF via
`request.security(..., lookahead=barmerge.lookahead_off)` and reference bar `[1]` so it
never repaints.

**Superseded first-pass blend:** ER + VR(4) + ATR-z on 1-min (below) — kept for the
record, but the multi-TF R²+VolSwitch+CUSUM design is better because it moves off the
*worst* detectability timeframe and adds calibrated thresholds + explicit change-point timing.

**Implemented as:** `nq_regime.pine` (MTF version) in this repo.

Two corrections to the first-pass thresholds:
  - **Hurst's random-walk baseline is ~0.545, NOT 0.5** (Qian & Rasheed 2004, Monte Carlo).
    So "H>0.55 = trend" is nearly a coin flip — use **H>0.65** if using Hurst at all.
  - **Variance Ratio is fragile intraday** (Andersen-Bollerslev-Das 2001): "not statistically
    robust... within a high-frequency context." It only becomes significant at weekly. Don't
    lean on VR intraday.

---

## The single most important framing result

**Safari & Schmidhuber 2025** ([arXiv:2501.16772](https://arxiv.org/abs/2501.16772),
14 yr of index-futures tick data): index futures **mean-revert below ~15–30 minutes**,
transition around 30 min–a few hours, and **trend from ~1 hour to days**.

→ A 1-min strategy operates in the reversion-favorable sub-30-min window. BUT that
short-horizon "reversion" is largely **magnitude** (bid-ask bounce / non-synchronous
trading), **not directional reversal** (Portnaya 2026,
[arXiv:2606.29591](https://arxiv.org/abs/2606.29591): SPY lag-1 autocorr −0.081, z=−7.4,
but the *sign* test is insignificant, p=0.11).

**Practical implication:** most regime statistics sit very close to their random-walk
value almost all the time on 1-min index futures. The tradeable signal is thin and slow.
Fast, self-normalizing measures survive; laggy/statistically-heavy ones don't.

---

## Method-by-method

### 1. Hurst Exponent — WEAK intraday, skip as a live gate
- H > 0.5 trending/persistent; H < 0.5 mean-reverting/anti-persistent; H = 0.5 random walk.
- Compute via R/S, aggregated-variance, or **DFA** (most robust on noisy 1-min: cumulative
  sum → detrend each window → F(n)=√mean-sq-residual → regress log F(n) vs log n → slope = H).
- **Verdict:** 1-min index-futures H stays ≈0.5 essentially always once estimation error is
  accounted for ([arXiv:0712.2910](https://arxiv.org/abs/0712.2910),
  [arXiv:1201.4786](https://arxiv.org/abs/1201.4786)). Needs 100–500 bars, laggy, noisy.
  Uncorrected R/S has an upward small-sample bias (reports H>0.5 for a true random walk).
  Use only as a slow strategic overlay, not a per-trade gate.
- Estimator formulas reference: [arXiv:2310.19051](https://arxiv.org/abs/2310.19051).

### 2. Variance Ratio (Lo-MacKinlay 1988) — YES, confirmation axis
- `σ²(1)` = var of 1-bar returns; `σ²(q)` = var of q-bar (overlapping) returns / q.
  **VR(q) = σ²(q)/σ²(1)**. VR>1 trend, VR<1 revert, VR=1 random walk.
- Homoskedastic significance (Pine-light): `Z = (VR−1)/√φ(q)`, `φ(q)=2(2q−1)(q−1)/(3qT)`;
  |Z|>1.96 rejects random walk. (Heteroskedastic-robust Z* is too heavy — skip.)
- **Key identity:** `VR(q) = 1 + 2·Σⱼ(1−j/q)·ρ(j)` → VR(2)=1+ρ(1). It IS a weighted sum of
  autocorrelations; higher q smooths out bid-ask bounce. So VR *subsumes* Method 5.
- Params: q ∈ {2,4,8,16}, T ≈ 100–390 one-min bars (T ≥ 10q). Caveat: U-shaped diurnal
  volatility distorts VR if the window straddles open/close.
- Formulas: [Mingze Gao's Lo-MacKinlay notes](https://mingze-gao.com/posts/lomackinlay1988/).

### 3. ADX / Directional Movement (Wilder 1978) — laggy, confirmation only
- Pine built-in `ta.dmi(14,14)` → [+DI, −DI, ADX]. ADX>25 trending, <20 ranging.
  Direction is NOT in ADX (comes from +DI vs −DI).
- **Verdict:** double-smoothed → laggy (~150 bars to settle), whipsaws on 1-min, can peak
  right before a reversal. Critically it does **not** separate "trend that continues" from
  "strong impulse about to revert" — both spike ADX. Keep only as optional trend-danger
  confirmation. Refs: StockCharts ChartSchool, Fidelity.

### 4. Kaufman Efficiency Ratio (Smarter Trading 1995) — BEST pure intraday gauge
- `ER = |close − close[N]| / Σ_{i=1..N} |close − close[i-1... ]|` = net move ÷ path length.
  ER→1 efficient/trending, ER→0 choppy/mean-reverting.
- Thresholds: ER>0.5–0.6 trending, ER<0.3 (band 0.25–0.35) choppy. Asset-relative — prefer
  percentile/adaptive gating over hard cutoffs. Default N=10 (Kaufman's KAMA), 20 smoother.
- **Verdict:** single-pass ratio, essentially no smoothing → far less laggy than ADX,
  reacts within N bars, self-normalizing to [0,1]. The engine inside KAMA. **The workhorse.**
  Directionless (keep separate direction logic). Ref: StockCharts KAMA page.

### 5. Autocorrelation of Returns — use VR instead
- Rolling ρ(k): Pine `ta.correlation(r, r[k], N)` with `r = log(close/close[1])`.
  ρ(1)>0 trending, ρ(1)<0 mean-reverting, significant when |ρ|>1.96/√N.
- **Caveat:** bid-ask bounce injects spurious *negative* lag-1 autocorr (small on 1-min
  liquid NQ, decays within a few 1-min lags). Mitigate: use front-month continuous/mid,
  prefer lag-5/10 or VR(4)/VR(8), calibrate the neutral band empirically (1-min NQ shows a
  mildly-negative baseline even in neutral regimes). **Prefer VR — same statistic, less noise.**

### 6. Regime-Switching (HMM) — can't fit in Pine, but the proxy is clear
- Pine can't do EM/matrices. But the literature is clear the fit isn't needed: HMM states
  trained on returns+volatility align with calm/trend vs turbulent/revert, and the
  transition-matrix diagonal *is* hysteresis.
- **Computable proxy:** one trend-efficiency measure (ER or inverse Choppiness) + one
  volatility measure (ATR z-score) → composite score → threshold with hysteresis.
- Choppiness Index alt: `CHOP = 100·log10(Σta.tr(n)/(highest(high,n)−lowest(low,n)))/log10(n)`,
  CHOP>61.8 ranging / <38.2 trending (Fibonacci thresholds, n≈14).
- Refs: [arXiv:2104.03667](https://arxiv.org/pdf/2104.03667),
  [arXiv:2006.08307](https://arxiv.org/pdf/2006.08307) (HMM intraday ES momentum).

---

## Hysteresis is essential (the causal analog of an HMM transition matrix)

A raw threshold cross flip-flops. Stabilize with any/all of:
1. **Deadband** — asymmetric enter/exit (enter DIRECTIONAL at score ≥ +0.15, only leave at ≤ −0.15).
2. **N-consecutive-bar confirmation** — the score must persist N bars before switching.
3. **Min-dwell cooldown** — hold a regime a minimum number of bars before it can flip.
4. Smooth the composite score before thresholding.

---

## The honest warning — regime classifiers rarely give a standalone edge

**Most on-point paper:** the MNQ-specific classifier
([arXiv:2605.11423](https://arxiv.org/abs/2605.11423), 947 days of 5-min MNQ) builds a
regime flag from 3 pre-market observables (first-30-min return magnitude, overnight gap,
opening-volume z-score). Classifier-positive days show morning drift + a systematic
**14:00–15:30 late-session reversal** — but **every directional strategy built on it failed
validation after costs.**

This matches this repo's own `fade-filters-hurt` finding: entry filters that look
statistically sound repeatedly backtest net-negative once removed-trade W/L is checked.

**Therefore:** build the regime indicator as **context** (which account/config to run), not
as a standalone trade trigger. Validate any regime-gated strategy with the removed-trade
discipline before shipping.

---

## How this maps to this repo's strategies

| Regime | Favorable strategy here |
|--------|--------------------------|
| **DIRECTIONAL** | Zone Rider "Denver" in Distance mode (trend-amplified); slope momentum |
| **MEAN-REVERSION** | The original fade concepts (Zone Rider fade, slope reversion) |

The 2021–2026 NQ sample was predominantly *directional/up*, which is exactly why the fade
configs backtested net-negative and the trend-follow Zone Rider (breach-hold + trailing
floor) scored PF 1.85, 6/6 years. A regime tool tells you *when* to switch sides.

---

## Full citation list

- [arXiv:2501.16772](https://arxiv.org/abs/2501.16772) — time-scale thresholds (reversion <30min, trend >1hr). The framing paper.
- [arXiv:2606.29591](https://arxiv.org/abs/2606.29591) — short-horizon reversion is magnitude, not direction.
- [arXiv:2605.11423](https://arxiv.org/abs/2605.11423) — MNQ-specific regime classifier; honest negative result after costs.
- [arXiv:0712.2910](https://arxiv.org/abs/0712.2910), [arXiv:1201.4786](https://arxiv.org/abs/1201.4786) — 1-min index-futures Hurst ≈ 0.5.
- [arXiv:2310.19051](https://arxiv.org/abs/2310.19051) — Hurst estimator formulas (R/S, aggregated-variance, DFA).
- [arXiv:2103.02091](https://arxiv.org/abs/2103.02091) — Hurst bias / min-length.
- [arXiv:2205.11122](https://arxiv.org/abs/2205.11122) — Hurst as the momentum/reversion switch.
- [arXiv:2104.03667](https://arxiv.org/pdf/2104.03667), [arXiv:2006.08307](https://arxiv.org/pdf/2006.08307) — HMM regime literature.
- [Mingze Gao — Lo-MacKinlay notes](https://mingze-gao.com/posts/lomackinlay1988/) — variance ratio formulas.
- [StockCharts KAMA](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama) — Efficiency Ratio formula.
- StockCharts ChartSchool (ADX), Fidelity (ADX) — directional movement.

---

# PART 2 — Multi-Timeframe Regime Detection (the better design)

**Bottom line:** the 1-min finding wasn't a limitation of the methods — it's a property of
the instrument. Roll up. Judge regime on **1-hour** (or daily veto), execute on 1-5min.

## Which timeframe is best? (detectability rises with bar size)

- **[VERIFIED] Safari & Schmidhuber 2025** (arXiv:2501.16772): trending regime lives from
  **~1 hour to ~1-2 years**, peaks at **3-12 months**; reversion below ~30 min and above ~2 yr.
- **[VERIFIED] Ernie Chan 2016**: SPY intraday Hurst = **0.494** (random); daily Hurst =
  **0.469** (significantly mean-reverting). Signal only appears at daily scale.
  *(Correction: the "16-32 day momentum→reversion switch" often cited is GLD/gold, not SPY.)*
- **[VERIFIED] Kroha & Škoula 2018 (DAX)**: Hurst = **0.54 at 1-day** returns vs **0.82 at
  50-day** — same series, effect size grows ~50× purely by lengthening the horizon.

Ranking: **daily over multi-month lookback** (strongest) > daily/multi-day > **1-hour**
(low edge of the trending regime, usable) > 1/5/15-min (≈ random walk, worst).

## Do the classic methods work better above 1-min? Yes, with 2 caveats

- **[VERIFIED] Hurst random-walk baseline is ~0.545, not 0.5** (Qian & Rasheed 2004 Monte
  Carlo: mean 0.5454, 95% band 0.45-0.64). Use **H>0.65**, not 0.55 — the retail rule sits
  inside the noise band.
- **[VERIFIED] VR is fragile intraday even with huge N** (Andersen-Bollerslev-Das 2001):
  "not statistically robust... seriously misleading within a high-frequency context." VR
  only becomes significant at weekly (Lo-MacKinlay VR(2)=1.30 weekly CRSP).
- **ADX** needs ~150 bars to stabilize (Wilder) — structurally unsuited to short intraday windows.
- **Aggregation artifact**: some higher-TF "trendiness" is overlapping-returns mechanically
  accumulating autocorrelation — don't over-trust monotonic Hurst-vs-horizon curves.

## Multi-timeframe "regime-on-higher, execute-on-lower" — insurance, not alpha

- **[SOURCED] Bhatti (SSRN)** — HTF momentum state gating LTF mean-reversion entries:
  Sharpe 0.592 → 0.837, but only 10%-significant; framed as "crash insurance."
- **[VERIFIED, skeptical] setup4alpha**: tested 12 regime filters on SPY/QQQ 2000-26 —
  **11 of 12 cost money vs buy-and-hold.** A breadth filter dodged 77%/86% of 2008/COVID
  drawdown but ended at ~0.5× buy-and-hold. → regime filters help **drawdown/win-rate more
  than net P&L.** Validate removed-trade W/L (this repo's standing discipline).
- **Repaint hazard**: naive MTF backtests leak future info. Use
  `request.security(..., lookahead=barmerge.lookahead_off)` and reference the *confirmed*
  prior HTF bar `[1]`. (nq_regime.pine does this.)
- **Prefer 1-hour regime over daily** for a 1-5min executor — a daily state can hide
  intraday reversals; match the regime lookback closer to the trade horizon.

## Better models than ER+VR+ATR (ranked, Pine-computable)

- **A. Rolling regression R² + slope — strongest upgrade over ER.** Calibrated 95%
  significance table: **N=10→0.40, 14→0.27, 20→0.20, 30→0.13, 50→0.08, 120→0.03.** Above
  = significant trend. `ta.correlation(close, bar_index, N)^2`; direction from `ta.linreg`
  slope. ER's textbook mapping backtests *inverted* (Alvarez) — another reason to use R².
- **B. Volatility Switch (McEwan, TASC 2013)** — normalized vol, threshold 0.5: below
  (falling vol) = trending mode, above = mean-reversion mode. Already Pine-ported (LazyBear).
  Cheapest robust trend/fade gate. EWMA variance `σ²ₙ=λσ²ₙ₋₁+(1−λ)r²ₙ₋₁`, λ≈0.94.
- **C. Online 2-state Hamilton/Markov filter** — highest fidelity, but needs params
  (transition matrix, per-regime μ,σ) **pre-fit offline** in the Python harness. Then it's a
  scalar Bayes update, no matrix inversion. arXiv:2402.08051. Feasible in Pine only if pre-fit.
- **D. Permutation entropy** — Bandt-Pompe ordinal entropy; low = structured/directional,
  high = random/chop. Cheap, noise-robust. Lower priority than A/B.

## Change-point detection — telling you WHEN it changed

Immovable law: lower false-alarm rate ⇄ longer detection lag.

- **[VERIFIED] Tabular CUSUM — best fit for Pine.** Two scalars: `sPos=max(0, sPos+z−k)`,
  `sNeg=max(0, sNeg−z−k)`; fire when either > `h`, then reset. `k`≈0.5 (detect ~1σ), `h`≈4-5.
  Pure recursion. (NIST handbook.)
- **[VERIFIED] Page-Hinkley** — one-sided CUSUM of fading-mean deviation; no history stored.
  River defaults: delta=0.005, threshold=50, alpha=0.9999, min_instances=30.
- **[VERIFIED] BOCPD (Adams & MacKay)** — principled, online, but run-length vector is O(t)/step
  → needs pruning to fit Pine array limits. More than needed for a regime toggle.
- **N-bar confirmation** — the baseline; explicitly *lagging, not leading*. Use only as a debounce.

**Verdict:** CUSUM gives *early* change-point flags with a tunable lag/false-alarm knob from
**2 scalars** — strictly better than N-bar confirmation for "tell me when it changed," and far
lighter than BOCPD or a filtered HMM.

## The recommended build (implemented in nq_regime.pine MTF)

- **Timeframe:** regime judged on **1-hour**, executed on your ladder. `request.security` with
  `lookahead_off`, referencing the confirmed prior HTF bar `[1]`.
- **Component 1 (state):** R² ≥ threshold (N-calibrated) + slope sign = directional; else revert.
- **Component 2 (confirm):** Volatility Switch (falling vol = trend, rising = fade) as a 2nd vote.
- **Component 3 (change-point):** CUSUM on standardized 1h returns → the "when it changed" flag
  (can shortcut the min-dwell so a real break flips early).
- **Hysteresis:** N-bar debounce + min-dwell so the label doesn't flip-flop.

## PART 2 citations

- [arXiv:2501.16772](https://arxiv.org/abs/2501.16772) — timeframe regimes (trend 1hr–yrs).
- [Ernie Chan 2016](http://epchan.blogspot.com/2016/04/mean-reversion-momentum-and-volatility.html) — SPY Hurst 0.494 intraday / 0.469 daily.
- Kroha & Škoula 2018 (DAX) — Hurst 0.54 @ 1d vs 0.82 @ 50d.
- [Qian & Rasheed 2004](https://c.mql5.com/forextsd/forum/170/hurst_exponent_and_financial_market_predictability.pdf) — Hurst RW baseline 0.545, use 0.65.
- [Andersen-Bollerslev-Das 2001](https://public.econ.duke.edu/~boller/Published_Papers/jf_01.pdf) — VR fragile intraday.
- [tradingpedia R²](https://www.tradingpedia.com/forex-trading-indicators/r-squared-method/) — R² critical-value table.
- [Volatility Switch (LazyBear/McEwan)](https://www.tradingview.com/script/50YzpVDY-Volatility-Switch-Indicator-LazyBear/).
- [NIST CUSUM handbook](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc3231.htm); [River Page-Hinkley](https://riverml.xyz/dev/api/drift/PageHinkley/).
- [setup4alpha](https://setup4alpha.substack.com/p/i-tested-12-smart-money-regime-filters) — 11/12 regime filters lost money (skeptical counterweight).
- arXiv:2402.08051 (online Hamilton filter), arXiv:0710.3742 (BOCPD), Bhatti SSRN 6087107 (MTF gating).

*Compiled 2026-07 for the pinescripts repo. Indicator: `nq_regime.pine` (MTF: 1h regime, R²+VolSwitch+CUSUM).*
