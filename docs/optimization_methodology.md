# Strategy Optimization & Validation Methodology

How this repo decides whether a change to a strategy is a **real edge** or a **curve-fit artifact**.
Distilled from the slope_touch_fade work (Aug 2026) but meant to apply to any strategy here. The
core belief: on 1-min index futures almost any tweak can be made to show a positive 5yr net — the
job is to reject the ones that only look good, *before* trusting them with money.

---

## 0. The reference oracle (never skip)

Every fast/optimized backtest must reproduce the **validated pure-Python port**
(`slope_touch_fade_bt.py`) bar-for-bar — same trades, same net — before its results are trusted.
The port itself was validated against the TradingView Strategy Tester to the dollar. Speed and
convenience never override this chain: `.pine` ⇄ port ⇄ fast engine must agree.

---

## 1. The metrics we judge on (and why net is the weakest)

Never decide on **net P&L alone** — on a tail-heavy strategy a few trades dominate net, so a config
can post a big number while being fragile. We look at, in rough order of trustworthiness:

| Metric | What it catches |
|---|---|
| **exTop10 / exTop50** (net with the N best trades removed) | **tail-dependence.** If net goes negative after removing ~10 trades, the "edge" is luck, not process. THE most important filter here. |
| **Per-year positivity** (how many of the 6 years are net-positive) | robustness across regimes; a config that's 6/6 is real, 3/6 is fitted to a couple of hot years. |
| **Median trade** | is the *typical* trade profitable, or is the mean a mirage propped up by the tail? |
| **Profit factor (PF)** | gross-win / gross-loss; less tail-sensitive than net. |
| **Win %** | secondary; a fade can be <50% and still fine if winners > losers. |
| **Net / avg** | the headline — but read LAST, and never in isolation. |

Rule of thumb from this repo: **top-10 trades ≈ 100%+ of net = fragile; exTop10 strongly positive
= broad-based edge.** (slope-touch-fade N=90: exTop10 +3,985 on +8,124 net → real. Many rejected
variants: exTop10 negative → tail-luck.)

---

## 2. In-sample vs out-of-sample — the distinction that killed the most ideas

- **In-sample / contemporaneous** relationships (e.g. "best-N correlates with the current regime")
  are easy to find and frequently REAL — but not tradeable, because you can't know the current
  regime label without hindsight bias creeping in.
- **Out-of-sample / predictive** is the only thing that pays: decide the parameter from data
  STRICTLY BEFORE the period you trade.
- **Walk-forward** is how we test predictiveness: e.g. weekly N picked from the trailing 4 weeks,
  trade the next week, concatenate all next-weeks → an honest OOS curve
  (`walkforward_fast.py`). Adaptive-N *looked* promising in-sample and DIED in walk-forward — that
  gap is the whole point of running it.

The separate OOS month (`~/Downloads/data.csv`, a Pine strategy export with exact S/R+ols columns)
is the bar-exact cross-check; the raw 5yr is the recompute path for sweeps.

---

## 3. Techniques we used (the toolbox)

- **Parameter sweep + inverted-U reading.** Sweep one lever across a wide range; trust a clean
  single-peaked curve (N=90 was the top of a smooth inverted-U 30→300), distrust a lone spike in an
  otherwise-bad region (N=40's net looked good but sat between bad neighbors → tail-fit trap).
- **Freeze-then-verify.** When changing detector logic (e.g. freeze-at-dot pullback), apply it to
  `.pine` + port + exporter together, then assert trade totals still reconcile.
- **Removed-trade W/L.** Before shipping any *filter*, look at the win/loss of the trades it REMOVES.
  A filter that removes net-losers is real; one that removes a mix (or removes winners) is noise.
  (Multiple entry filters were rejected this way — see fade-filters-hurt.)
- **Regime bucketing.** Tag trades by an independent regime label (1h R²+slope classifier,
  `regime.py`, ported from nq_regime.pine) and compare per-bucket — reveals *where* an edge lives.
- **Session/time attribution.** Bucket net by London hour; the slope-touch edge clustered at
  London-open, NY-open, NY-midday (a *keep*-hours filter, not a block filter). Session structure is
  a legitimate, mechanically-explainable axis; a scattered hour pattern is not.
- **Slippage sensitivity** (carry from slope-strategy work): thin/high-freq edges evaporate at
  0.5–1pt slippage; a result that only survives at 0-slip is not real.

## 4. Anti-patterns we explicitly reject

- **Net-chasing.** A higher 5yr net with worse exTop10 / fewer positive years is a *worse* config.
- **Tail-fit spikes.** One lucky parameter value in a bad neighborhood.
- **Scan-and-pick-best** detectors (dynamic-N via window scan): scanning always finds *some*
  qualifying window, inflating trade count with marginal setups — more trades, same net, worse
  per-trade quality. Rejected on both slope-touch-fade and per the earlier live_trend work.
- **Cutting the runners.** Break-even stops, tight trails, straightness exits — all repeatedly LOSE
  because this family of strategies is carried by the trailing tail; clipping it kills the edge.
- **Un-backtestable changes shipped on faith.** If a change can't be measured offline (needs live
  data we don't have, or only exists in Pine), it is a *hypothesis to forward-watch*, not a result.

## 5. Compute (so validation stays cheap enough to actually do)

The discipline above only works if runs are fast enough to iterate. The detector is an O(n×N)
rolling OLS — pure Python was ~42–90s/run, making sweeps 10–15 min and walk-forward worse.
**Fix: numba @njit** on the detector + trade loop (`fast_detect.py`, `fast_sim.py`) → bar-exact,
~90x (15-value sweep 13min → 8.6s; walk-forward → 2s). NOT Spark/DuckDB — the sim is a stateful
bar-by-bar recurrence, not a query. See `backtest/PERF_NOTES.md`.

## 6. The honest-outcome principle

Report what the data says, not what we hoped. Several strong-sounding ideas were **rejected** by
this process (dynamic-N, adaptive-N walk-forward, most entry/exit filters, VWAP-band fades) and that
is a *success* of the method, not a failure of the session. A confirmed-negative ("price-only
adaptive-N doesn't predict next week") is valuable — it's what justified moving to options-derived
signals rather than guessing.

---

### Where the pieces live
- Reference: `backtest/slope_touch_fade_bt.py` (port), `~/Downloads/data.csv` (bar-exact OOS).
- Fast engine: `backtest/fast_sim.py`, `fast_detect.py`; perf rationale `backtest/PERF_NOTES.md`.
- Sweeps: `sweep_olsN.py`, `walkforward_fast.py`, `n_by_regime.py`, `regime.py`.
- Regime research: `docs/regime_detection_research.md`; options plan `docs/options_regime_plan.md`.
