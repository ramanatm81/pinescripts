# Slope Strategy -- Exit Criteria

## Overview

The strategy uses a 10-bar OLS slope (`legSlope`) of non-doji closes as the entry signal.

- **Long** entry: `legSlope < -slopeEntry` (downtrend -- mean reversion up expected)
- **Short** entry: `legSlope > +slopeEntry` (uptrend -- mean reversion down expected)

Entry labels on chart:
- Green **S↑** / Red **S↓** -- shallow entry (`abs(legSlope) < deepSlope`)
- Orange **D↑** / Orange **D↓** -- deep entry (`abs(legSlope) >= deepSlope`)

Each label shows: entry price, SL locked in, and entry slope.
Each exit label shows: exit type, entry slope (es:), exit slope (xs:).

---

## Entry Filter -- Trail Direction Block

After a **TRAIL** exit, the opposite direction is blocked at the next potential entry bar
if `legSlope` is still trending in the same direction as the trail exit:

- Trail exited Short (`trailExitDir=-1`) → Long blocked while `legSlope < -slopeEntry`
- Trail exited Long (`trailExitDir=+1`) → Short blocked while `legSlope > +slopeEntry`

The block persists indefinitely and only clears when a new trade actually enters.
This prevents fading a still-trending market immediately after a trail exit.

---

## Exit Priority Order

### 1. BLK -- Session Block Exit

**Trigger:** A trade is open when entering a configured block window.

| Toggle                        | Window (CT)   | CT Minutes |
|-------------------------------|---------------|------------|
| Block NY open first 30 min   | 08:30-09:00   | 510-540    |
| Block LN open first 30 min   | 02:00-02:30   | 120-150    |
| Block CME pre-open + NY open | 07:30-09:00   | 450-540    |

- All toggles default to **off**
- No cooldown after BLK -- block window itself prevents re-entry
- Label: gray **BLK**

---

### 2. EOD -- End of Day Close

**Trigger:** `ctMins >= 900` (15:00 CT) while position is open.

- Always active, not configurable
- Closes all positions, resets all state, no cooldown
- No chart label (strategy engine closes it)

---

### 3. SL -- Hard Stop Loss

**Trigger:** Price moves against entry by `activeSL` points.

- Long: `low <= entryPrice - activeSL`
- Short: `high >= entryPrice + activeSL`

`activeSL` is locked in at the entry bar:

| Mode            | Condition                   | SL used                       |
|-----------------|-----------------------------|-------------------------------|
| Fixed (default) | `enableSmaSL = false`       | `slPts` (default 50 pts)      |
| SMA dynamic     | `close > SMA` at entry      | `slAboveSma` (default 50 pts) |
| SMA dynamic     | `close < SMA` at entry      | `slBelowSma` (default 30 pts) |

- Active for all entries
- Triggers cooldown after exit
- Label: red **SL**

---

### 4. THRD -- Hard Time Expiry

**Trigger:** Trade open >= N bars AND `legSlope` still strongly against the trade.

Conditions (all must be true):
- `enableTExpHard = true` (default: off)
- `barsInTrade >= tExpHardBars` (default: 20 bars)
- Long: `legSlope <= -tExpHardSlope` (downtrend still persisting)
- Short: `legSlope >= +tExpHardSlope` (uptrend still persisting)

Key behaviour:
- Fires regardless of P&L
- Does NOT fire if slope has weakened or recovered -- only when still strongly against
- Counted in the no-traction stats table

**Example:** Long open 20 bars, `legSlope=-1.5`, `tExpHardSlope=1.0` -- THRD fires.
Long open 20 bars, `legSlope=-0.4` -- THRD does not fire (slope recovering).

- Label: maroon **THRD**

---

### 5. TEXP -- Profitable Time Expiry

**Trigger:** Trade open >= N bars AND currently in profit.

Conditions (all must be true):
- `enableTExp = true` (default: off)
- `barsInTrade >= tExpBars` (default: 30 bars)
- Long: `close > entryPrice`
- Short: `close < entryPrice`

Key behaviour:
- Will NOT fire if trade is underwater
- Captures slow drifting profits before they reverse

- Label: blue **TEXP**

---

### 6. TRAIL -- Trailing Stop

**Trigger:** Price moves `trailTrigger` pts in profit, then retraces `trailDist` pts from best price.

- Long: activates when `bestPrice - entryPrice >= trailTrigger`; fires when `low <= bestPrice - trailDist`
- Short: activates when `entryPrice - bestPrice >= trailTrigger`; fires when `high >= bestPrice + trailDist`

Key behaviour:
- Active for ALL entries (shallow and deep)
- Trail ratchets up with best price, never moves against trade
- After firing, sets `trailExitDir` to block opposite direction if trend still intact
- Defaults: trigger = 40 pts, distance = 20 pts

- Label: green **TRAIL**

---

### 7. TP -- Take Profit

**Trigger:** Price reaches fixed target set at entry.

- Long: limit at `entryPrice + tpPts x tpMult`
- Short: limit at `entryPrice - tpPts x tpMult`
- Managed by TradingView `strategy.exit()` engine
- Defaults: `tpPts=40`, `tpMult=3.0` -- TP at 120 pts from entry

- Label: green **TP**

---

## Exit Summary Table

| Exit  | Always | Configurable | Needs profit | Slope condition |
|-------|--------|--------------|--------------|-----------------|
| BLK   | if toggle on | toggle | No | No |
| EOD   | Yes | No | No | No |
| SL    | Yes | SL amount | No | No |
| THRD  | if enabled | N bars + slope | No | Yes -- slope against |
| TEXP  | if enabled | N bars | Yes | No |
| TRAIL | Yes | trigger + dist | No | No |
| TP    | Yes | pts x mult | No | No |

---

## Stats Table (bottom-right corner)

| Row                | Description                                        |
|--------------------|----------------------------------------------------|
| No-traction (THRD) | Count of THRD exits                                |
| Avg bars held      | Average bars held for THRD exits                   |
| Live bars in trade | Current bars in open trade (0 if flat)             |
| -- Deep entries -- | Separator showing deepSlope threshold              |
| Total              | Total closed trades with deep entry slope          |
| Wins / Losses      | Count of profitable vs losing deep trades          |
| Win rate           | Win rate % for deep entry trades                   |
| Avg P&L (pts)      | Average P&L in points for deep entry trades        |

---

## Data Window Plots

| Name          | Description                                      |
|---------------|--------------------------------------------------|
| legSlope      | Rolling 10-bar OLS slope (entry signal)          |
| tradeLegSlope | OLS slope of closes since entry bar              |
| activeSL      | Stop loss distance locked in at entry            |
| SMA           | SMA(180) used for dynamic SL decision            |
| inTrade       | 1 when in a trade, 0 otherwise                   |
| tradeDir      | 1=Long, -1=Short, 0=flat                         |
| barsInTrade   | Bars elapsed since entry                         |
| cooldown      | Bars remaining in cooldown                       |
| isDoji        | 1 if current bar is doji (excluded from slope)   |

---

## Parameters Reference

| Parameter        | Default  | Group         | Description                              |
|------------------|----------|---------------|------------------------------------------|
| `slopeEntry`     | 1.7      | General       | Entry threshold (abs value)              |
| `slPts`          | 50 pts   | General       | Fixed SL when SMA SL disabled            |
| `tpPts`          | 40 pts   | General       | TP base points                           |
| `tpMult`         | 3.0      | General       | TP multiplier (TP = tpPts x tpMult)      |
| `trailTrigger`   | 40 pts   | Trailing Stop | Profit pts before trail activates        |
| `trailDist`      | 20 pts   | Trailing Stop | Distance trail follows best price        |
| `enableTExp`     | false    | Time Expiry   | Enable profitable time exit              |
| `tExpBars`       | 30 bars  | Time Expiry   | Bar limit for TEXP                       |
| `enableTExpHard` | false    | Time Expiry   | Enable hard time exit                    |
| `tExpHardBars`   | 20 bars  | Time Expiry   | Bar limit for THRD                       |
| `tExpHardSlope`  | 1.0      | Time Expiry   | Slope-against threshold for THRD         |
| `dojiPct`        | 10%      | R2 Filter     | Body % below which bar is doji           |
| `cooldownBars`   | 10 bars  | R2 Filter     | Bars to wait after any exit              |
| `deepSlope`      | 3.0      | R2 Filter     | Threshold for deep entry label and stats |
| `enableSmaSL`    | false    | SMA Stop Loss | Enable SMA-based dynamic SL              |
| `smaPeriod`      | 180      | SMA Stop Loss | SMA period                               |
| `slAboveSma`     | 50 pts   | SMA Stop Loss | SL when close > SMA at entry             |
| `slBelowSma`     | 30 pts   | SMA Stop Loss | SL when close < SMA at entry             |
