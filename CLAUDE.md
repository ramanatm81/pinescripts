# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Pine Script indicators and strategies for TradingView, built around a **mean-reversion ladder** concept applied to NQ/MNQ futures (and other instruments with ETH/RTH sessions).

There is no build system. Scripts are pasted directly into TradingView's Pine Script editor. Syntax is validated there, not locally.

## Scripts overview

| File | Type | Purpose |
|------|------|---------|
| `mean_reversion.pine` | `indicator` | Core mean-reversion ladder — detects impulse/reversion/extension cycles from a session anchor |
| `mean_reversion_strategy.pine` | `strategy` | Same detection logic wired to automated entries (fade extensions) and exits (on continuation or next impulse) |
| `regime_change.pine` | `indicator` | Detects bullish/bearish regime from consecutive qualifying-body candles |
| `rolling_window_graph.pine` | `indicator` | Rolling N-bar mini candlestick chart + range stats in a table panel |
| `20pointsdown` | `indicator` | Flags consecutive-down-candle pattern with configurable thresholds and dual time windows |
| `20pointsup.pine` | `indicator` | Same as above for up moves (Pine v5) |

## Core architecture — mean reversion scripts

Both `mean_reversion.pine` and `mean_reversion_strategy.pine` share the same state machine. The strategy file adds trade entry/exit logic on top.

### Session anchors
- Two resets per day: **ETH reset** (default 17:00) and **market open** (default 09:30)
- On reset: anchor = open of the reset bar, all state cleared
- **Skip window**: optional period (configurable start → market open) where no signals fire
- **Loiter reset**: if anchor sits idle > N minutes with no impulse, anchor moves to current close (orange marker)

### Thresholds
- Two separate point thresholds: `thresholdPtsRTH` (default 30 pts) and `thresholdPtsETH` (default 50 pts)
- `activeThreshold` switches automatically based on `inRTH` (09:30–17:00)

### State machine (per bar)
```
anchor set
  └─ not inImpulse
       ├─ high - anchor >= threshold  → Impulse UP  (green label, inImpulse=true)
       └─ anchor - low  >= threshold  → Impulse DOWN (red label, inImpulse=true)

  └─ inImpulse
       ├─ reached impulsePrice ± threshold → EXTENSION (purple)
       │    ├─ big body (≥ 2/3 threshold) → label as CONT instead
       │    ├─ anchor resets to close, inImpulse=false
       │    └─ starts continuation watch (trackCont)
       │
       └─ wick touched original anchor → REVERSION (fuchsia, marker only)
            └─ reversionFired=true; inImpulse stays true
                 └─ next impulse in any direction starts new cycle
```

### Continuation watch
After an extension, the script watches `contCandles` bars. If price hasn't pulled back ≥ half the threshold AND is still diverging at bar N, it fires a `CONT` (teal) label.

### State variables convention
- `var` declarations = persistent across bars (state)
- Plain `bool` declarations (e.g. `bool alertImpulseUp = false`) = reset to false every bar, set true when the event fires on that bar — used for `alertcondition` and strategy entries

### Strategy-specific (mean_reversion_strategy.pine)
- **Entry**: on `evExtension`, fade the direction (EXT up → short, EXT down → long)
- **Exit on CONT**: market kept going, cut the trade
- **Exit on next impulse**: reversion completed or cycle invalidated
- `tradeDir` tracks 1/−1/0 to avoid double-entries

## Pine Script version
All files use `//@version=6` except `20pointsup.pine` which uses v5. When editing, keep versions consistent within each file.

## Key conventions

- Time is represented as `hour(time) * 60 + minute(time)` minutes-since-midnight
- Session boundaries are parsed from HHMM strings (e.g. `"0930"`) at runtime
- Labels are placed at `barstate.islast` for live updating; permanent labels are placed when events fire
- `max_lines_count=500` / `max_labels_count=500` are set to handle busy sessions
- All timestamps stored as Unix milliseconds; elapsed time computed as `(time - savedTime) / 60000`
