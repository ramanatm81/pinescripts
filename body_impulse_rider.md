# Body Impulse Rider

## Overview

A momentum continuation/reversal strategy that identifies strong, clean-bodied impulse candles as reference points and trades the outcome of the next N bars.

---

## Reference Candle (REF)

The strategy begins each cycle by identifying a **reference candle** — a candle with genuine directional conviction:

- Body size ≥ 20 points (configurable)
- Upper wick ≤ 50% of body
- Lower wick ≤ 50% of body
- Only triggers when no watch window is currently active

Candles with large wicks are excluded because they signal indecision rather than momentum.

---

## Watch Window

After a REF is identified, the strategy monitors the next **5 bars** (configurable) for one of two outcomes:

### CONT — Continuation
- A candle in the **same direction** as the REF appears with a body ≥ **75% of the ref body** (configurable)
- Fires immediately when the condition is met — does not wait for the window to expire
- **Trade:** Enter in the same direction as the REF candle

### REV — Reversal
- A candle in the **opposite direction** to the REF appears with a body ≥ **100% of the ref body** (configurable)
- Fires immediately when the condition is met
- **Trade:** Enter in the opposite direction to the REF candle

### Silent Expiry
- The watch window expires with neither CONT nor REV firing
- No trade is placed; the cycle ends and waits for the next REF

---

## Exit Rules

Exits are evaluated in priority order:

1. **Stop loss** — 100 points against the entry price (configurable); always active
2. **Next REF while in loss** — position is closed immediately when the new REF candle appears
3. **Next REF while in profit** — position is left open; the stop loss manages the exit

---

## Session Filters

New entries are blocked during the first 30 minutes after three key session opens to avoid erratic open-range behaviour. Each filter is independently toggleable.

| Session | No-Entry Window (ET) | Hard Close At (ET) |
|---------|---------------------|--------------------|
| CME Open | 08:30 – 09:00 | 08:25 |
| NYSE Open | 09:30 – 10:00 | 09:25 |
| London Open | 03:00 – 03:30 | 02:55 |

### Hard Close
Five minutes before each blocked session open, any open position is **force-closed unconditionally** — regardless of profit or loss. This prevents being caught in the volatile open-range move with an unintended directional bias.

All times are computed in `America/New_York` and adjust automatically for DST.

---

## Signal Labels (on chart)

| Label | Colour | Meaning |
|-------|--------|---------|
| REF | Blue | Reference candle identified, watch window starts |
| CONT | Teal | Continuation confirmed, trade entered with trend |
| REV | Red | Reversal confirmed, trade entered against prior REF |
| ✕ CLOSE | Orange | Hard close — session open in 5 minutes |

---

## Configurable Inputs

| Input | Default | Description |
|-------|---------|-------------|
| Min Body Size | 20 pts | Minimum body for a candle to qualify as REF |
| Watch Window | 5 bars | Number of bars to monitor after a REF |
| Stop Loss | 100 pts | Points from entry price to stop |
| CONT Threshold | 75% | Min body size (% of ref body) for a CONT signal |
| REV Threshold | 100% | Min body size (% of ref body) for a REV signal |
| Block CME Open | On | Enable/disable CME open filter and hard close |
| Block NYSE Open | On | Enable/disable NYSE open filter and hard close |
| Block LDN Open | On | Enable/disable London open filter and hard close |

---

## Files

| File | Purpose |
|------|---------|
| `body_impulse_strategy.pine` | Full strategy with automated entries, exits, and stop loss |
| `body_impulse_watch.pine` | Indicator-only version — shows REF/CONT/REV labels with no trade execution |
