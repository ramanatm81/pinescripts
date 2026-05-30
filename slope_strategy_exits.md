# Slope Strategy -- Exit Criteria

## Overview

The strategy enters **Long** when `legSlope < -slopeEntry` (downtrend -- mean reversion expected up)
and **Short** when `legSlope > +slopeEntry` (uptrend -- mean reversion expected down).
All slope inputs are **absolute values** applied symmetrically by direction.

---

## Exit Types (priority order)

### 1. BLK -- Session Block Exit

**Trigger:** A trade is open when a configured block window starts.

| Toggle                        | Window (CT)   | CT Minutes |
|-------------------------------|---------------|------------|
| Block NY open first 30 min   | 08:30 - 09:00 | 510-540    |
| Block LN open first 30 min   | 02:00 - 02:30 | 120-150    |
| Block CME pre-open + NY open | 07:30 - 09:00 | 450-540    |

- All toggles default to **off**
- No cooldown after BLK -- the block window itself prevents re-entry
- Label: gray **BLK**

---

### 2. EOD -- End of Day Close

**Trigger:** Position still open at 15:00-16:00 CT.

- Always fires, not configurable
- Closes all positions unconditionally
- No chart label (closed by TradingView engine)

---

### 3. SLP -- Slope Recovery Exit *(deep entries only)*

**Trigger:** Entry slope was deep AND current slope has recovered past the exit threshold.

Conditions:
- Entry is deep when `abs(entrySlope) >= deepSlope` (default 3.0)
- Long: exit when `legSlope >= -deepExitSlope` (e.g. slope rises above -0.5)
- Short: exit when `legSlope <= +deepExitSlope` (e.g. slope falls below +0.5)

Key behaviour:
- Deep entries **skip trailing stop** -- SLP is the primary exit
- Hard SL remains active as a safety net
- `deepExitSlope` (default 0.5) controls how far slope must recover

**Example:** Long entered at slope -8.03. Holds until `legSlope >= -0.5`.
If price crashes hard before slope recovers, the hard SL fires instead.

- Label: orange **SLP**

---

### 4. SL -- Hard Stop Loss

**Trigger:** Price moves against entry by `activeSL` points.

- Long: `low <= entryPrice - activeSL`
- Short: `high >= entryPrice + activeSL`

`activeSL` is **locked in at entry bar** based on SMA condition:

| Mode           | Condition                   | SL used                   |
|----------------|-----------------------------|---------------------------|
| Fixed (default) | `enableSmaSL = false`      | `slPts` (default 50 pts)  |
| SMA dynamic    | `close > SMA(180)` at entry | `slAboveSma` (default 50 pts) |
| SMA dynamic    | `close < SMA(180)` at entry | `slBelowSma` (default 30 pts) |

- Active for both shallow and deep entries
- For deep entries: safety net if price crashes before slope recovers
- Label: red **SL**

---

### 5. THRD -- Hard Time Expiry *(slope against)*

**Trigger:** Trade open >= N bars AND slope still against the trade.

Conditions (all must be true):
- `enableTExpHard = true` (default: off)
- `barsInTrade >= tExpHardBars` (default: 20 bars)
- Long: `legSlope <= -tExpHardSlope` (downtrend persisting, reversal failed)
- Short: `legSlope >= +tExpHardSlope` (uptrend persisting, reversal failed)

Key behaviour:
- Fires **regardless of P&L** -- will exit a losing trade
- Does NOT fire if slope is flat or recovering -- only when still deeply against
- `tExpHardSlope` (default 1.0) sets the against threshold

**Example:** Long open 20 bars, slope still -1.5, `tExpHardSlope=1.0` --> THRD fires.
If slope recovered to -0.4, THRD does not fire.

- Label: maroon **THRD**

---

### 6. TEXP -- Profitable Time Expiry

**Trigger:** Trade open >= N bars AND currently in profit.

Conditions (all must be true):
- `enableTExp = true` (default: off)
- `barsInTrade >= tExpBars` (default: 30 bars)
- Long: `close > entryPrice`
- Short: `close < entryPrice`

Key behaviour:
- Will **not** fire if trade is underwater -- takes profit, never cuts losses
- Captures slow-drift profits that haven't hit TP or trail

- Label: blue **TEXP**

---

### 7. TRAIL -- Trailing Stop *(shallow entries only)*

**Trigger:** Price moved `trailTrigger` pts in profit, then retraced `trailDist` pts from best price.

Conditions:
- Long: trail activates when `bestPrice - entryPrice >= trailTrigger`; fires when `low <= bestPrice - trailDist`
- Short: trail activates when `entryPrice - bestPrice >= trailTrigger`; fires when `high >= bestPrice + trailDist`

Key behaviour:
- **Suppressed for deep entries** -- SLP manages those
- Trail ratchets with best price and never moves against the trade
- Defaults: trigger = 17 pts, distance = 9 pts

- Label: green **TRAIL**

---

### 8. TP -- Take Profit

**Trigger:** Price reaches `entryPrice +/- (tpPts x tpMult)`.

- Long: limit order at `entryPrice + tpPts x tpMult`
- Short: limit order at `entryPrice - tpPts x tpMult`
- Managed by TradingView `strategy.exit()` engine
- Defaults: `tpPts=40`, `tpMult=3.0` --> TP at 120 pts from entry

- Label: green **TP**

---

## Deep vs Shallow Entry Summary

| Exit    | Shallow entry      | Deep entry          |
|---------|--------------------|---------------------|
| Hard SL | Active             | Active (safety net) |
| Trail   | Active             | Suppressed          |
| SLP     | Never fires        | Primary exit        |
| TP      | Active             | Active              |
| TEXP    | Active if enabled  | Active if enabled   |
| THRD    | Active if enabled  | Active if enabled   |
| BLK     | Always             | Always              |
| EOD     | Always             | Always              |

> **Deep entry** = `abs(entrySlope) >= deepSlope` (default 3.0)

---

## Parameters Reference

| Parameter        | Default  | Group         | Description                          |
|------------------|----------|---------------|--------------------------------------|
| `slopeEntry`     | 1.7      | General       | Entry threshold (abs value)          |
| `slPts`          | 50 pts   | General       | Fixed SL fallback                    |
| `tpPts`          | 40 pts   | General       | TP base points                       |
| `tpMult`         | 3.0      | General       | TP multiplier (TP = tpPts x tpMult)  |
| `trailTrigger`   | 17 pts   | Trailing Stop | Profit pts before trail activates    |
| `trailDist`      | 9 pts    | Trailing Stop | Distance trail follows best price    |
| `deepSlope`      | 3.0      | R2 Filter     | Min abs(entrySlope) for deep mode    |
| `deepExitSlope`  | 0.5      | R2 Filter     | Slope recovery target for SLP exit   |
| `enableTExp`     | false    | Time Expiry   | Enable profitable time exit          |
| `tExpBars`       | 30 bars  | Time Expiry   | Bar limit for TEXP                   |
| `enableTExpHard` | false    | Time Expiry   | Enable hard time exit                |
| `tExpHardBars`   | 20 bars  | Time Expiry   | Bar limit for THRD                   |
| `tExpHardSlope`  | 1.0      | Time Expiry   | Slope-against threshold for THRD     |
| `enableSmaSL`    | false    | SMA Stop Loss | Enable SMA-based dynamic SL          |
| `smaPeriod`      | 180      | SMA Stop Loss | SMA period                           |
| `slAboveSma`     | 50 pts   | SMA Stop Loss | SL when close > SMA at entry         |
| `slBelowSma`     | 30 pts   | SMA Stop Loss | SL when close < SMA at entry         |