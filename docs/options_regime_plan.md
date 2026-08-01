# Options-Data Regime Signals — Build Plan

A reusable plan for adding **options-derived regime signals** to any strategy in this repo (fade,
trend, ladder, adaptive-N). Options data is *forward-looking* in a way price-only measures aren't —
it encodes what the market is pricing for future volatility, direction-fear, and dealer behaviour.
This doc is the sourcing + method + integration blueprint. **Not yet built — no options feed wired.**

Instrument context: we trade **MNQ/NQ** (Nasdaq-100 futures). Greeks are per-option; what we want are
**index/aggregate** options metrics from the NDX/QQQ chain, aligned to the futures.

---

## 1. What each signal tells us (ranked by regime value)

| Signal | Greek / source | Regime read | Use for |
|---|---|---|---|
| **VXN level** | implied vol (Nasdaq VIX) | high/rising = intense/directional; low/falling = calm/range | overall regime intensity |
| **VXN term structure** | front vs back IV | **backwardation** (front>back) = stress/trend; **contango** = calm/mean-revert | trend-vs-range flag |
| **VRP = VXN − realized** | IV minus NQ realized vol | IV rich vs realized → fades work (MR); realized > IV → directional break | **sharpest cheap axis** |
| **Skew / 25Δ risk reversal** | delta (strike select) + IV | steep put skew = crash-fear/directional-down; flat = complacent range | directional bias |
| **Dealer gamma (GEX)** | aggregate gamma × OI | **positive** = dealers dampen → pin/mean-revert (great to fade); **negative** = amplify → trend/breakout | the most regime-relevant greek |

Theta/rho: not regime-useful, skip. Vega matters only as the thing IV is priced from.

**Mechanical link to our strategies:** slope-touch-fade is a *fade* → it wants the **mean-reversion /
positive-gamma / contango / high-VRP** regime. A trend strategy wants the opposite. So one options
regime label can *route* which strategy (or which N, which side) is active — the "which account to
run" framing from [[nq_regime.pine]] / docs/regime_detection_research.md.

---

## 2. Where to get the data (tiered by cost/effort)

### Tier 1 — VXN, FREE, daily (START HERE)
- Yahoo `^VXN` history (CSV, back to ~2001): https://uk.finance.yahoo.com/quote/%5EVXN/history/
- Investing.com VXN (CSV): https://www.investing.com/indices/cboe-nasdaq-100-voltility-historical-data
- CBOE official dashboard: https://www.cboe.com/us/indices/dashboard/vxn/
- Also grab **VIX** and a 3-month vol proxy for the term-structure signal.
- **Daily is fine for a WEEKLY regime/N decision.** Unlocks: VXN level, term structure, and
  **VRP** (VXN − NQ realized, using futures we already have). ~80% of the value for $0.
- Agent can't fetch these hosts directly → **user downloads the CSV, drops it in `ohlcv/`**.

### Tier 2 — Databento OPRA (we already use Databento for futures)
- OPRA dataset: https://databento.com/datasets/OPRA.PILLAR — full historical NDX/QQQ chains
  (per-strike quotes + OI). Pay-as-you-go, **$125 free credits**, recently added 10yr history.
- Unlocks **skew** (25Δ RR) and **dealer GEX**. Heavy to pull/process (full chains × 5yr).

### Tier 3 — pre-computed surfaces
- ORATS (~$100/mo): pre-computed IV surfaces + Greeks (skip building the IV math).
- CBOE DataShop ($500/mo EOD, $1000 intraday): exchange-direct gold standard; overkill unless core.

---

## 3. Method — computing each signal offline (Python, causal)

All must be **causal / no-lookahead** (use the confirmed prior period), mirroring nq_regime.pine.

- **VXN level regime:** z-score VXN vs its own trailing window; high z = directional, low = range.
- **Term structure:** `ts = VXN_front − VXN_back` (or VXN − VIX3M-equiv). ts>0 backwardation=trend.
- **VRP:** `vrp = VXN − realized_vol(NQ, trailing)`. Annualize both to compare. High vrp = fade-friendly.
- **Skew:** from chain, IV at 25Δ put − 25Δ call. Needs Tier 2. Steep = down-fear.
- **GEX:** Σ over strikes of gamma_i × OI_i × contract_mult × spot², sign by dealer-position
  assumption (dealers short puts / long calls heuristic). Needs Tier 2 + honest caveat: the dealer
  sign convention is a heuristic, not ground truth — easiest signal to fool yourself with.

---

## 4. Integration pattern (reuse across strategies)

Produce a single per-bar (or per-week) **regime label / score** module — the same interface as the
price-only `backtest/regime.py` already built (returns +1 dir-up / −1 dir-down / 0 mean-revert). Then:

1. **As a strategy router:** run fade only when label = mean-reversion; trend only when directional.
2. **As an adaptive-N input:** feed the label/score into the weekly walk-forward N picker
   (`backtest/walkforward_N.py`) as a 4th predictor alongside OU-halflife and the vol-rule.
3. **As an entry gate:** block fade entries when GEX<0 (negative-gamma = amplify = fade fails).

Keep options signals **orthogonal** to price signals so they *add* information (VRP already blends
IV with realized — that's the point).

---

## 5. Validation discipline (non-negotiable — carry from the rest of this repo)

- **Walk-forward / OOS only.** Decide the regime/param from data STRICTLY before the traded period.
  Weekly-N harness already does this (4-week trailing → next week).
- **Per-year gate + tail test** (exTop10). A signal that only lifts net via a few tail trades is a
  fit, not an edge — see [[slope-touch-fade-N-sweep]], [[slope-strategy-abandoned]].
- **Report removed-trade W/L.** The repo's own research (docs/regime_detection_research.md HONEST
  NOTE; setup4alpha: 11/12 regime filters LOST vs buy-and-hold) says regime filters usually help
  **drawdown/win-rate more than net P&L**. Judge on the right axis, don't over-claim net.
- **Align timezones:** options data is usually US/Eastern EOD; our bars are CT-stored, London-shown.
  Convert carefully (see [[chart-london-tz]]).

---

## 6. Concrete first milestone (when options work resumes)

1. User downloads **VXN + VIX daily CSV** → `ohlcv/vxn_daily.csv`, `ohlcv/vix_daily.csv`.
2. Build `backtest/options_regime.py`: load VXN, compute VXN-z, term-structure, **VRP** (vs NQ
   realized). Per-day label, forward-filled to 1m, causal.
3. Add it as a **4th predictor** in `walkforward_N.py` and as a **router flag** the fade/trend
   strategies can read.
4. Gate: per-year + exTop10 + removed-trade W/L vs fixed baseline. Ship only if it survives.
5. If VRP/VXN helps → justify Tier 2 (Databento OPRA) for **GEX/skew**; else stop (feed not worth it).

---

## Reference

- Repo price-only regime work: `nq_regime.pine`, `chop_detector.pine`,
  `docs/regime_detection_research.md` (arxiv 2501.16772 Safari-Schmidhuber: 1m futures ~ random walk,
  judge regime on ~1h+; R² significance table; Volatility Switch; CUSUM change-point).
- Adaptive-lookback literature: shorter window in range / longer in trend, keyed off vol; the
  principled version sets lookback ≈ **OU mean-reversion half-life** = ln(2)/θ.
- Options-regime theory: dealer gamma (GEX) sign = mean-revert vs amplify; VRP = IV−RV as a
  fade-friendliness gauge; term-structure backwardation = stress/trend.
