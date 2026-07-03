# Research: 1-minute NQ/MNQ intraday strategy edges

Synthesized from multiple research passes during strategy development. Every
effect below is a **hypothesis to re-test on your own bars** — the exact
thresholds are indicative. Windows in **ET** unless noted (NQ Globex opens
18:00 ET = 17:00 CT; RTH = 09:30–16:00 ET = 08:30–15:00 CT; **ET − 1h = CT**).

> **Overriding caveat.** A systematic 947-day MNQ study (2021–2025, 14 signal
> families) found raw OHLCV intraday edges are only ~0.07–1.50 pts/trade —
> marginal after costs, none passing full robustness. Treat everything here as
> directional guidance, not settled constants.

---

## 0. What our own backtests proved (18-day sample, Jun–Jul 2026)

- **Momentum / breakout LOSES on 1-min NQ.** Donchian breakout, Opening-Range
  Breakout, Supertrend-follow, EMA-cross — all net-negative. The 1-min chart
  chops too much for breakouts to pay.
- **Only mean-reversion has an edge here.** This is *why* the slope-fade
  strategy works and why the VWAP-distance reversion works.
- Best distinct (non-slope) strategy found: **VWAP-distance reversion** — fade
  when price ≥ 1×ATR from session VWAP, in an elevated-ATR regime, tight 20/5
  trail, drop 3 net-loser overnight hours. Realistic (1pt slippage) ≈ **1.5×**
  the slope baseline; a clean 2× was NOT achievable without unfillable sub-5pt
  trai
- ls.
- **Combining slope-fade + VWAP did not help** — VWAP is the stronger signal;
  union/confluence/regime-route all diluted it.
- **Sizing by signal magnitude would HURT** — verified: the most-extreme
  ATR-distance trades are the *worst* (regime-break risk), not the best.
- Our time-of-day result **disagreed with the literature** (below): on our data
  the VWAP-reversion made money during the RTH open / power hour, which the
  literature calls hostile. → time-of-day needs the 5-year data to settle.

---

## 1. Time-of-day edge (mean-reversion)

**Reversion-FAVORABLE**
- **11:30–13:30 ET (10:30–12:30 CT) — lunch trough. Best reversion window.**
  Volume ~9–13% of daily vs ~20–29% at open; false-breakout rate 45–55% (vs
  25–30% at open) → breakouts fail and revert. Trending-bar share drops to ~38%.
- **Fade large overnight/gap moves during RTH.** Overnight→intraday reversal on
  equity index futures has Sharpe ~2–5× conventional daily reversal.

**Reversion-HOSTILE (disable fades or invert to breakout)**
- **09:30–10:30 ET (08:30–09:30 CT) — RTH open.** Most volatile 30 min (~3–4×
  midday per-minute vol); ~62% trending bars; NQ opening range ~70–100 pts.
  Fading here is the single worst timing (in the literature).
- **15:00–16:00 ET (14:00–15:00 CT) — power hour.** MOC imbalance (15:50 ET),
  ~$5–10B typical flow → directional continuation into the close. Do not fade.
- **Intraday-momentum link:** 09:30–10:00 return predicts 15:30–16:00 return,
  R²≈2% (up to 3.5% combined). Both ends of the day are momentum-aligned.

**Overnight / ETH (18:00 ET → 09:30 ET)**
- Spreads widen to ~1.0–1.5 NQ pts vs ~0.25–0.50 RTH → higher reversion
  breakeven. Behaves like slow trend-continuation in a thin book; Asia/London
  news causes outsized moves. **Size reversion down or off overnight.**

**Signal decay:** intraday reversal from liquidity/bid-ask bounce resolves in
**under 1 hour**, strongest at ~15-min spacing. Don't hold fades for a slow pull.

---

## 2. Volatility-regime position sizing

- **ATR risk sizing (primary):** `Contracts = Risk$ / (k · ATR · PointValue)`,
  k ≈ 1.0–1.5 for 1-min, ATR lookback ~5 bars. MNQ = $2/pt, NQ = $20/pt.
  Auto-shrinks size when ATR expands (open, FOMC).
- **Inverse-vol overlay:** `mult = clamp(target_vol / realized_vol_20d, 0, 2)`,
  target ~10–12% annualized, cap 2×. Vol-targeting lifted Sharpe ~+0.2–0.4 in
  studies (but weaker out-of-sample per JFE rebuttal — test it).
- **ATR-percentile gate:** full size only in the low/normal band; cut hard above
  the 90th percentile (stress). Low-vol/range favors reversion; high-vol/trend
  favors momentum.
- **VIX nuance:** reversion *signal* edge best in a moderate band (VIX ~15–20);
  degrades above 30 where trend risk dominates — yet VIX itself mean-reverts, so
  per-trade edge can rise with vol even while *sizing* should shrink.
- **Kelly cap:** run ¼–½ Kelly as a ceiling; recompute W/R every 50–100 trades.
- **We verified on our data:** magnitude sizing by ATR-distance is *inverted*
  here (extreme distance = worst trades). Don't naively size up on extremes.

---

## 3. Consecutive-loss / equity-curve filters — mostly HURT

- Only add edge if trade P&L is **positively autocorrelated (lag-1 ≥ +0.2)**.
  If trades are independent, the filter just shrinks the sample (gambler's
  fallacy). **Validate with runs-test + Ljung-Box ACF + Monte-Carlo shuffle.**
- **For mean-reversion the naive filter is BACKWARDS** — MR equity curves are
  *negatively* autocorrelated (losses cluster in trends, then snap back), so
  "stop after N losses / trade only above equity-MA" turns you off right before
  the bounce. ConnorsRSI trade-above-200MA = −29% CAR; larger stops beat smaller.
- What helps (narrow): **fade your own drawdown** (trade only when equity is
  *below* its MA) → lower MaxDD & higher PF, but ~30% less net profit.
- Prefer a **graduated size-down** or an explicit regime filter (ADX<25 or
  Hurst<0.5) over a hard on/off switch. (Trend filters lag, so they help less
  than hoped.) The slope strategy's existing "deep-loss block" is closer to a
  regime/context filter than a blind streak counter — the more defensible design.

---

## 4. Day-of-week / session effects

- **Monday = worst for reversion** (lowest gap-fill ~54%, highest variance).
- **Tue–Thu = best for gap-fade** (Thu SPY gaps fill ~82% vs Mon ~65%).
- **Wed 1%+ gap-UPS trend (~67% keep rising) — do NOT fade.**
- **Friday = tightest ranges** — reversion works, smaller targets.
- **Turn reversion OFF:** FOMC 14:00 ET; all 08:30 ET Tier-1 releases (CPI/NFP/
  GDP → 100–400 NQ pts in 5 min, be flat pre-8:30, re-engage 8:35–8:40);
  quad-witching Fridays (swings 50–100% larger).
- **Turn-of-month** has a long bias (last day + first ~3 days) — shorts into
  month-turn strength face a headwind.

---

## 5. First-hour range (Initial Balance) as a filter

`IB = high−low of 09:30–10:30 ET`, normalized by ATR:
- **WIDE opening range (IB/ATR ≥ 1.0) = exhaustion day → reversion-friendly.**
  Double-break rate ~5.7% (0% for IB > 1.5×ATR). Fade these days.
- **NARROW opening range (IB/ATR < 0.5) = expansion/trend day → SUPPRESS fades.**
  Trend-day probability ~68% vs 52% avg; double-break ~6–7× higher.
- **~75% of days set the daily high OR low within the first 60 min.** After
  10:30 ET, don't fade a move needing a *fresh* daily extreme.

---

## 6. Exit timing for snapbacks

- **Kevin Davey's 567k-backtest study:** fixed **dollar/point targets beat
  trailing stops**, which beat **time-based exits** (5–45 bars underperformed);
  **dollar stops beat ATR stops.** → use a tight fixed target as the money-maker,
  time-stop only as a fail-safe.
- **Half-life sizing:** fit AR(1)/Ornstein-Uhlenbeck on anchor-relative price →
  half-life = −ln2/λ; set N-bar time-stop ≈ 1–2× half-life.
- **MAE/MFE derived levels:** initial stop just beyond the 80–90th-percentile
  MAE of *winning* fades; target near the median MFE of past winners. Derive
  per-instrument from your own trade log.
- **Scale out:** 30–40% at the mean, 30–40% at ~1.5 SD beyond, hold 20–30% for
  the tail.
- **Our data caveat:** the tight 20/5 trail *did* work for VWAP-reversion — but
  a fixed target is worth A/B-testing on the 5-year data (Davey says it wins).

---

## 7. Signal-combination methods (for 2+ mean-reversion signals)

1. **Confluence (AND)** — trade only when both agree → fewer trades, higher
   win-rate/PF, total profit may fall. Failure: over-filtering + both fire
   together right before a trend-continuation (they agree because the move is
   violent, which is when MR fails).
2. **Union (OR) + conflict resolution** — trade either; on opposite-direction
   conflict, skip (safest) or defer to the stronger/regime-owning signal. More
   trades, more total profit, diluted win-rate.
3. **Strength/agreement sizing** — size by #signals agreeing or magnitude. ONLY
   valid if magnitude is monotonic with expectancy (we verified it is NOT here).
4. **Regime-routing** — signal A in one regime, B in another, with an ATR
   **hysteresis band** (e.g. flip to high-vol at 1.20×, back at 0.90×) to avoid
   whipsaw. Most principled when the signals have genuinely different regime edges.
5. **Meta-labeling (rule-based)** — primary signal picks direction; a secondary
   rule-stack (other signal confirms + ADX cap + regime sane + trend-day kill +
   not-too-extreme) decides take/skip. Improves precision; keep to ≤4–5 rules to
   avoid overfitting. Label via triple-barrier (TP/SL/time) to validate each rule.
6. **Ensemble voting** across N signals; raise the vote threshold to slide from
   OR→AND. Watch for **correlated voters** (many "far from a moving average"
   signals = one signal in disguise).

**The one filter that protects all of them:** a **trend-day kill-switch** —
suppress all mean-reversion when `relative_ATR > cap` OR `ADX > cap` OR
`|session_return| > cap`. This removes the fat left tail every MR strategy shares
and often adds more to Sharpe than the combination logic itself.

---

## Recommended build order (fastest path to a robust improvement)

1. Verify sign conventions; bucket each signal's per-trade P&L by strength
   quintile (is magnitude monotonic with expectancy? — decides if sizing is valid).
2. **Regime-routing** with ATR hysteresis (VWAP owns high-ATR; slope owns calm).
3. **Meta-label veto layer**: other-signal-agrees + ADX cap + trend-day kill.
4. **Vote-threshold sweep** to pick the frequency/quality operating point.
5. **Conviction sizing last**, only if step 1 showed monotonicity.
6. Re-derive exits from MAE/MFE; A/B fixed-target vs trail (Davey favors target).

Report **profit factor, win-rate, trade count, max drawdown, Sharpe** for every
variant vs the standalone baselines. A combination that doesn't beat `max(A,B)`
on risk-adjusted return isn't worth the complexity.

---

## Key sources (for your reference)
- MNQ 947-day systematic study — arxiv.org/abs/2605.04004
- Intraday momentum R² — SSRN 2552752
- Sub-1-hr reversal — arxiv 1005.3535 (Heston-Korajczyk-Sadka)
- Vol-managed portfolios — Moreira-Muir NBER w22208 (+ JFE rebuttal, Cederburg et al.)
- Equity-curve/random-data — Carver, qoppac.blogspot.com
- MR equity-curve filters — alvarezquanttrading.com, setup4alpha.substack.com
- Exit study (567k backtests) — kjtradingsystems.com (Kevin Davey)
- U-shape volume/vol — Jain-Joh; tosindicators.com; volatilitybox.com
- Session NQ point figures — volatilitybox, tosindicators, tradealgo (indicative)

---

## 8. 5-YEAR WALK-FORWARD VERDICT (the decisive test)

Ran both strategies on the full 5-year MNQ continuous front-month (1.77M 1-min
bars, 2021-06 → 2026-06), realistic 1pt slippage. This overturns the 18-day
conclusions.

**VWAP-reversion (my "2x challenge" strategy) = a 5-YEAR LOSER:**
| year | pnl | win |
|------|-----|-----|
| 2021 | -6436 | 55% |
| 2022 | -4358 | 60% |
| 2023 | -7518 | 56% |
| 2024 | -5730 | 58% |
| 2025 | +4830 | 60% |
| 2026 | +11184 | 63% |
| **5yr** | **-8648** | 59%, PF 0.99 |
Profitable in only 2 of 6 years. The 18-day sample (Jun-Jul 2026) was its ONE
good regime → it was overfit to a favorable window.

**Slope-fade (the existing strategy) = ROBUST:**
| year | pnl | win |
|------|-----|-----|
| 2021 | -40 | 60% |
| 2022 | +5924 | 60% |
| 2023 | -1659 | 58% |
| 2024 | +3095 | 61% |
| 2025 | +11797 | 62% |
| 2026 | +11479 | 62% |
| **5yr** | **+30578** | 61% |
Profitable in 4 of 6 years; the 2 losing years are small. A durable edge.

**Lessons:**
1. 18-day backtests are dangerous — both "edges" and "failures" can be regime
   artifacts. ALWAYS validate on the 5-year data now.
2. The slope-fade has a real, multi-regime edge; don't destabilize it chasing
   marginal 18-day gains.
3. Any new strategy/filter must show **profitability across most of the 6 years**
   before it's trusted — full-period PnL alone is not enough (2025-26 can carry
   a losing 2021-24).

---

## 9. Fukuoka optimization validated on 5 years (holds up)

The 18-day Fukuoka tuning (slopeEntry 1.7->2.5, trailDist 10->8, tpPts 40->50,
tExpBars 30->20) was re-tested on the full 5yr. It GENERALIZES — not overfit:

| config | 5yr pnl | win | profitable yrs |
|--------|---------|-----|-----|
| pre-Fukuoka (1.7/10/40/30) | +13,464 | 55% | 4/6 |
| **Fukuoka (2.5/8/50/20)**  | **+30,578** | **61%** | 4/6 |

Per-parameter on 5yr:
- slopeEntry: flat optimum (1.7-3.0 all ~+29-30.5k) — robust, not knife-edge; 2.5 near peak.
- trailDist=8: monotonically best (8:+30.5k, 10:+23.9k, 12:+18.4k). Tighter wins, and 8 is fillable.
- tpPts: nearly irrelevant (trail does the exiting).
- tExpBars=20: beats 30 (+30.6k vs +24.7k, 61% vs 56% win).

Conclusion: Fukuoka more than DOUBLED 5yr PnL vs pre-Fukuoka and every param
checks out across regimes. The slope strategy + Fukuoka defaults is the
validated, robust system. (Optional: slopeEntry 2.0 or 3.0 give 5/6 profitable
years vs 4/6 for 2.5, at trivial PnL cost — 2021 is +/-0 either way.)
