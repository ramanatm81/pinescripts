# VWAP-Bands RTH Open Analyzer -- Requirements Document

Purpose: a UI to explore the behavior of the VWAP +/-2 sigma bands around the US RTH open,
over a selectable date range, using the statistics and logic we derived in analysis. This
document is the spec for building that UI later.

---

## 1. Data source

### 1.1 The 5-year dataset
- File: `ohlcv/mnq_5yr.csv` (in the repo; gitignored due to size, ~113 MB, ~1.77 M rows).
- Instrument: **MNQ** (Micro E-mini Nasdaq-100 futures, front month).
- Bar size: **1-minute** bars.
- Columns: `time, open, high, low, close, Volume`.
- Time span: **2021 through mid-2026** (roughly 5 years). ~1,289 trading days that have a valid RTH-open window.
- Timestamp format: ISO 8601. Some rows are UTC (`+00:00`), naive rows should be treated as UTC. The dataset's last bar is 2026-06-23.

### 1.2 Timezone handling (critical -- do not skip)
Three different timezones are in play and each is used deliberately:
- **Display / chart timezone: Europe/London.** All user-facing times and the date-range picker are in London time. This matches the user's TradingView chart.
- **VWAP daily anchor: London day.** The VWAP and its sigma bands RESET at London midnight (the chart-day boundary), NOT at UTC midnight and NOT at the CME session open. (We tested a 13:30-London / 07:30-CT 1-hour-pre-RTH anchor -- it made the bands too tight and everything pierced; the London-day anchor is the correct default. See section 6.)
- **Session windows (RTH / EOD): America/Chicago (CT).** RTH open = 08:30 CT = 14:30 London. EOD = 15:00 CT = 21:00 London. These are anchored to CT so they don't shift with the display timezone.

Key fixed times:
| Event | CT | London (BST) |
|---|---|---|
| RTH open | 08:30 | 14:30 |
| RTH-open window end | 09:00 | 15:00 |
| EOD (close/flat) | 15:00 | 21:00 |

Note London can be GMT (winter) or BST (summer); convert with a proper tz library (zoneinfo), not a fixed offset.

---

## 2. Core computed series (per bar)

### 2.1 Daily-anchored VWAP +/-2 sigma bands
- k = 2.0 (sigma multiplier).
- Reset accumulators at each new **London** day.
- Per bar: typical price tp = (high+low+close)/3; weight = Volume (use 1.0 if volume is 0/missing).
- Running: cumV += w; cumPV += tp*w; cumPPV += tp*tp*w.
- mean = cumPV/cumV; variance = max(cumPPV/cumV - mean^2, 0); sd = sqrt(variance).
- upper (+2 sigma) = mean + 2*sd ; lower (-2 sigma) = mean - 2*sd.
- "bands formed" = (upper - lower) >= 1.0 pt (early-session sigma is ~0, treat as not-formed).

### 2.2 The RTH-open window
- Window = 14:30-15:00 London (08:30-09:00 CT), the first 30 minutes = a 30-minute opening range.
- "open" reference level = the **open of the 14:30 bar**.
- Require at least ~5 valid formed-band bars in the window for a day to count.

### 2.3 Pierce detection
- Resistance pierce (a "resistance day"): a bar's **high >= upper band** during the window.
- Support pierce (a "support day"): a bar's **low <= lower band** during the window.
- A day can be resistance, support, both, or neither.

---

## 3. Metrics the UI must compute (over the selected date range)

All of these were derived in analysis and should be reproducible in the UI for any date subset.
Reference values below are the full-5yr numbers (the UI should recompute for the chosen range).

### 3.1 Frequency (per section 2 of the stats doc)
- % of days that pierce resistance (5yr: ~33%).
- % of days that pierce support (~28%).
- % neither (~42%), resistance-only, support-only, both.

### 3.2 Window range
- High-low range within 14:30-15:00 per day: mean/median/p90 (5yr: median ~102, mean ~114, p90 ~192).

### 3.3 Directional move on pierce days
- Resistance: open -> window high (5yr median ~72, mean ~79).
- Support: open -> window low (5yr median ~79, mean ~91).

### 3.4 Full-day range on pierce days
- Whole London-day high-low (5yr resistance median ~275 / p90 ~513; support median ~280 / p90 ~584).

### 3.5 Pierce geometry (resistance reference)
- open -> band-at-first-cross (median ~33 all days; but only ~16 on FAST pierces -- see 3.8).
- band -> window high (overshoot).

### 3.6 Timing within the window (minute 0 = 14:30)
- Minute of first band cross (median ~2, i.e. very fast).
- Minute of the window extreme (median ~19).
- % of days where the extreme comes AFTER the cross (~76%, price keeps running past the band).

### 3.7 Reversion / close behavior (the key stats)
- % of pierce days where price returns to TOUCH the open after the pierce, by EOD: **~76%** (res 75%, sup 78%).
- % of pierce days that CLOSE still on the pierced side of the open: resistance ~64% above, support ~60% below.
  IMPORTANT distinction: "touches open" (76%) is a fleeting dip; "closes on pierced side" (60-64%) is where it ends up. Both true simultaneously.
- Buy-at-open / hold-EOD drift in the pierce direction: all resistance days mean ~+44.8, median ~+60.5, 64% close up.
  (Winners-only subset median ~+124 is CONDITIONAL -- do not present as an expectancy.)

### 3.8 Position at 15:00 and pierce SPEED (runaway vs reverter)
- % of pierce days still beyond the band at 15:00 (~15%) vs already back inside (~85%).
- Revert-to-open rate split: still-beyond-at-15:00 ~42% revert; already-inside ~75% revert.
- Pierce speed: fast pierces (tag band within 1 min) revert ~88%; slow (10-30 min) ~64%. (Fast = overreaction that snaps back.)
- Slope at pierce (legSlope, 10-bar linear-regression slope of closes): steeper up-slope = LESS revert
  (negative slope ~89% revert, slope 20+ ~33% revert). Steep pierce = genuine trend/runaway.

### 3.9 Runaways (~24%)
- ~24% of pierce days NEVER return to the open (the "runaways") -- the strong trend days.
- These carry the buy-at-open drift but are not cleanly catchable (you only know it's a runaway after the run).

---

## 4. Views the UI should provide

### 4.1 Date-range selector (primary control)
- User selects a start and end date (London calendar dates). This is the main filter the user cares about.
- All metrics in section 3 recompute for the selected range only.
- Optional quick presets: full 5yr, per calendar year, last N days.

### 4.2 Per-day detail view
For a single selected day, show:
- 1-min candles for the London trading day (or at least 14:30-21:00).
- Overlaid VWAP mean, +2 sigma, -2 sigma bands.
- Markers: the 14:30 open level (horizontal line), pierce bar(s), the window extreme, and whether/when price returned to the open.
- Day classification: resistance / support / both / neither; fast vs slow pierce; closed above/below open.

### 4.3 Aggregate stats panel (for the selected range)
- All the section-3 metrics as a summary table (frequencies, ranges, reversion %, close-side %, speed split).
- Distributions (histograms) for: window range, directional move, minutes-to-pierce, revert-or-not.

### 4.4 Day-list / table
- One row per pierce day in the range, columns: date, direction (res/sup), pierce minute, window range, open->extreme, returned-to-open (y/n), closed-side, full-day range.
- Sortable/filterable. This lets the user eyeball individual days behind the aggregates.

---

## 5. Filters (secondary controls)
- Direction: resistance-only / support-only / both.
- Pierce speed: all / fast (<=N min) / slow.
- Position at 15:00: still-beyond-band / back-inside.
- (Optional) slope-at-pierce bucket.
These let the user slice the same range by the runaway-vs-reverter features from section 3.8.

---

## 6. Anchor variants (analysis toggle, optional)
We tested three VWAP anchors; the UI could let the user compare them, but London-day is the default:
- **London-day anchor (default, recommended):** wide bands, pierce is rare (~58% of days pierce something), meaningful extreme. Best signal.
- 13:30-London (1hr pre-RTH) anchor: bands too tight, ~93% of days pierce, signal washed out. (Tested; worse.)
- 14:30 RTH-open anchor: even tighter/later-forming; bands don't exist until ~14:45. (Not recommended.)

---

## 7. Important caveats to surface in the UI (so the analysis is not misread)
1. "Touches open" (76%) is NOT "closes at open" -- most pierce days (60-64%) close back on the pierced side. Price dips to the open then resumes.
2. The buy-at-open drift (~+45) is real but entry-locked: you cannot buy at the open because direction is only known after the pierce (~min 2), by which point price has left the open.
3. The ~24% runaways carry the directional drift but are only identifiable after the fact.
4. These are STATISTICS, not a validated trade. Every mechanical fade of the pierce (tight SL / no SL / trailing / fade-at-exhaustion) lost money under honest fills once look-ahead was removed. Long-only continuation was weakly positive but fragile. The UI is for VIEWING behavior, not a signal to trade blindly.

---

## 8. Implementation notes
- The stats/metrics logic already exists as ad-hoc Python in the chat history and in `backtest/cluster_breakdown_5yr.py` (VWAP-band + pierce computation). Reuse that band/pierce logic as the backend.
- Reference stat document: `docs/rth_open_pierce_stats.md` (has the numbered findings that map to section 3 here).
- Backend suggestion: load the CSV once, precompute bands + per-day pierce classification, then filter by date range on demand (the per-day loop is fast enough over 1.77M rows for offline use).
