"use strict";
// Replay Backtest frontend. Loads runs from the FastAPI backend, renders candles + S/R + trade
// markers with lightweight-charts, and replays the precomputed per-bar frames. No strategy logic
// lives here -- the backend serves frozen frames; this file only fetches windows and draws them.

const LWC = window.LightweightCharts;
const $ = (id) => document.getElementById(id);
const fmt = (x, d = 2) => (x === null || x === undefined) ? "—" : Number(x).toFixed(d);

const state = {
  tag: null, meta: null, trades: [], nBars: 0,
  cur: 0,                    // current bar index (the "playhead")
  winLen: 750,              // chart window size in bars
  win: null,               // {lo, hi, frames: array-of-per-bar-objects}
  playing: false, speed: 5, rafPending: false, lastTick: 0,
  activeTrade: -1,
  // active FILTER view -- scrub/replay/seek are confined to [viewLo, viewHi). Default = whole run.
  index: null,             // /run/{tag}/index payload (months + contracts)
  filterMode: "month",
  viewLo: 0, viewHi: 0,
};
const clampView = (idx) => Math.max(state.viewLo, Math.min(state.viewHi - 1, idx));

// ---- lightweight-charts setup ----
// IMPORTANT: the chart MUST be created with the container's real (laid-out) size. If created at
// zero width (before CSS flex layout settles) the internal time scale corrupts permanently and the
// canvas stays blank forever -- resize() does NOT recover it. So we create with explicit w/h and
// only after the layout is ready (init() runs from requestAnimationFrame).
let chart, candle, resSeries, suppSeries, stopSeries;
function createChart() {
  const el = $("chart");
  chart = LWC.createChart(el, {
    width: el.clientWidth, height: el.clientHeight,
    layout: { background: { color: "#0e1117" }, textColor: "#8b949e" },
    grid: { vertLines: { color: "#161b22" }, horzLines: { color: "#161b22" } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#2a313c" },
    rightPriceScale: { borderColor: "#2a313c" },
    crosshair: { mode: LWC.CrosshairMode.Normal },
  });
  candle = chart.addCandlestickSeries({
    upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
    wickUpColor: "#26a69a", wickDownColor: "#ef5350",
  });
  resSeries = chart.addLineSeries({ color: "#ef5350", lineWidth: 1, lineStyle: 2,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  suppSeries = chart.addLineSeries({ color: "#26a69a", lineWidth: 1, lineStyle: 2,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  stopSeries = chart.addLineSeries({ color: "#d29922", lineWidth: 2, lineStyle: 0,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  // real resize handler: keep the canvas matched to the container
  new ResizeObserver(() => chart.resize(el.clientWidth, el.clientHeight)).observe(el);

  // HOVER: update the bar-details panel as the mouse moves over bars (the user navigates by
  // hovering the monthly chart, not the replay). param.time is the hovered bar's epoch seconds.
  chart.subscribeCrosshairMove((param) => {
    if (!param || param.time == null) { renderState(); setPanelHover(false); return; }  // left chart
    const f = state.tsIndex ? state.tsIndex.get(param.time) : null;
    if (f) { renderState(f); setPanelHover(true); }
  });
}
function setPanelHover(on) {
  const h = $("statePanel").querySelector("h3");
  h.innerHTML = on ? 'Hovered bar <span class="dim">· times London</span>'
                   : 'Current bar <span class="dim">· times London</span>';
}

// London (Europe/London) UTC offset in SECONDS for a given instant -- +3600 in BST, 0 in GMT.
// Computed via Intl so DST is handled automatically. Cached by yyyy-mm to avoid recomputing per bar.
const _ldnOffCache = new Map();
function londonOffsetSec(date) {
  const key = date.getUTCFullYear() * 100 + date.getUTCMonth();
  if (_ldnOffCache.has(key)) return _ldnOffCache.get(key);
  // format the instant as London wall-clock, reparse as if UTC, diff = the offset
  const p = {};
  for (const x of _LDN.formatToParts(date)) p[x.type] = x.value;
  const asUTC = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  const off = Math.round((asUTC - date.getTime()) / 1000);
  _ldnOffCache.set(key, off);
  return off;
}

// epoch seconds the CHART is fed. lightweight-charts renders a UNIX `time` axis in UTC (NOT the
// browser tz), so to make the axis read Europe/London wall-clock we ADD the London offset -- the
// UTC-rendered label then equals London/BST. DST-correct because the offset is per-instant.
const toTs = (iso) => {
  const d = new Date(iso);
  return Math.floor(d.getTime() / 1000) + londonOffsetSec(d);
};

// Backend stores CT (e.g. "...-05:00"); the UI displays Europe/London to match TradingView. The
// text panels convert the stored CT-ISO to London wall-clock via the ldn* helpers below. The CHART
// axis is made London-correct by toTs() shifting the epoch by the London offset (see above).
// Formats: "MM-DD HH:MM" and "YYYY-MM-DD HH:MM:SS".
const _LDN = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});
function ldnParts(iso) {
  const p = {};
  for (const x of _LDN.formatToParts(new Date(iso))) p[x.type] = x.value;
  return p;  // {year,month,day,hour,minute,second}
}
const ldnFull = (iso) => { const p = ldnParts(iso); return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`; };
const ldnShort = (iso) => { const p = ldnParts(iso); return `${p.month}-${p.day} ${p.hour}:${p.minute}`; };
const ldnMin = (iso) => { const p = ldnParts(iso); return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`; };

// ---- data fetching ----
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
function showLoading(on) { $("loading").classList.toggle("hidden", !on); }

// Fetch a window [lo,hi) of frames as an array of per-bar objects (backend returns columnar).
async function fetchWindow(lo, hi) {
  lo = Math.max(0, lo); hi = Math.min(state.nBars, hi);
  const cols = "i,time,o,h,l,c,res,supp,anchor,run,r2,pos,entry_px,stop_level,stop_kind," +
               "cum_usd,unreal_usd,entry_dir,exit_reason,exit_px,long_sig,short_sig,long_arm,short_arm";
  const d = await api(`/run/${state.tag}/frames?from=${lo}&to=${hi}&cols=${cols}`);
  const n = d.n, out = new Array(n);
  const col = d.data;
  for (let k = 0; k < n; k++) {
    const o = {};
    for (const c of d.columns) o[c] = col[c][k];
    out[k] = o;
  }
  return { lo: d.lo, hi: d.hi, frames: out };
}

// Ensure the window covers `idx` (with margin); refetch if idx nears an edge.
async function ensureWindow(idx) {
  const w = state.win;
  const margin = Math.floor(state.winLen * 0.15);
  if (w && idx >= w.lo + margin && idx < w.hi - margin) return;   // still comfortably inside
  const lo = Math.max(0, idx - Math.floor(state.winLen / 2));
  const hi = lo + state.winLen;
  showLoading(true);
  state.win = await fetchWindow(lo, hi);
  drawWindow();
  showLoading(false);
}

// paint the whole current window onto the chart (candles + S/R lines up to `cur`)
function drawWindow() {
  const w = state.win; if (!w) return;
  const candles = [], resL = [], suppL = [];
  const tsIndex = new Map();      // epoch-seconds -> frame, for crosshair-hover lookups
  // Rails are PER-DAY levels. Two things make them readable over a multi-day window:
  //  1. break the line between sessions (a whitespace point) so yesterday's rail does not slope
  //     across the night into today's -- lightweight-charts joins consecutive points otherwise.
  //  2. once a side has filled, the OPPOSITE rail is dead for that day -- stop drawing it, so the
  //     chart shows only the level that actually mattered.
  let prevDay = null, sideTaken = 0, prevTs = null;
  for (const f of w.frames) {
    const t = toTs(f.time);
    candles.push({ time: t, open: f.o, high: f.h, low: f.l, close: f.c });
    const day = (f.time || "").slice(0, 10);   // CT date -- the RTH session key
    if (day !== prevDay) {
      // Break the line between sessions. lightweight-charts joins consecutive points, so without
      // this you get one long line spanning days at levels that were never simultaneously live --
      // yesterday's rail drawn straight through today's chart. A whitespace point is {time} with
      // NO `value` key. The bars here are contiguous 1-min data (no overnight hole), so the cut
      // slot is prevTs+1 -- one second after the last bar of the old day, which no bar occupies.
      // Do NOT gate this on a time gap between sessions: there is none, and the break never fires.
      if (prevDay !== null && prevTs !== null) {
        resL.push({ time: prevTs + 1 });
        suppL.push({ time: prevTs + 1 });
      }
      prevDay = day; sideTaken = 0;
    }
    if (f.entry_dir) sideTaken = f.entry_dir;
    const showUp = sideTaken >= 0;         // up rail dies once a SHORT filled
    const showDn = sideTaken <= 0;         // down rail dies once a LONG filled
    if (f.res != null && showUp) resL.push({ time: t, value: f.res });
    if (f.supp != null && showDn) suppL.push({ time: t, value: f.supp });
    tsIndex.set(t, f);
    prevTs = t;
  }
  state.tsIndex = tsIndex;
  candle.setData(candles);
  resSeries.setData(resL);
  suppSeries.setData(suppL);
  drawMarkersAndStop();
}

// PULLBACK FROM THE DOT: the reference is FROZEN at the arm bar (the strategy waits out from the
// dot, not from a deeper extreme). For the entry at window-index ke, find its arm bar and measure
// the pullback as entry_px vs the arm bar's low (long) / high (short). Returns {frame, px,
// pullbackPts} or null if the arm bar isn't in the loaded window.
function extremeForEntry(frames, ke) {
  const e = frames[ke];
  const isLong = e.entry_dir === 1;
  const armKey = isLong ? "long_arm" : "short_arm";
  let armK = -1;
  for (let k = ke; k >= 0; k--) { if (frames[k][armKey]) { armK = k; break; } }
  if (armK < 0) return null;
  const refPx = isLong ? frames[armK].l : frames[armK].h;   // frozen origin = arm bar's extreme
  const pull = isLong ? (e.entry_px - refPx) : (refPx - e.entry_px);
  return { frame: frames[armK], px: refPx, pullbackPts: pull };
}

// entry/exit markers for the WHOLE current view (all trades shown at once, not clipped to the
// playhead). The active-stop line still tracks only up to `cur` (it's a live level, not an event).
function drawMarkersAndStop() {
  const w = state.win; if (!w) return;
  const markers = [], stopL = [];
  for (let fi = 0; fi < w.frames.length; fi++) {
    const f = w.frames[fi];
    const t = toTs(f.time);
    // ARM dot: trend-into-S/R detected, BEFORE the pullback entry (the .pine's red/green dot).
    // green = long arm at support (below bar), red = short arm at resistance (above bar).
    if (f.long_arm)
      markers.push({ time: t, position: "belowBar", color: "#26a69a", shape: "circle", text: "•" });
    if (f.short_arm)
      markers.push({ time: t, position: "aboveBar", color: "#ef5350", shape: "circle", text: "•" });
    if (f.entry_dir === 1 || f.entry_dir === -1) {
      const isLong = f.entry_dir === 1;
      markers.push({ time: t, position: isLong ? "belowBar" : "aboveBar",
        color: isLong ? "#26a69a" : "#ef5350", shape: isLong ? "arrowUp" : "arrowDown",
        text: isLong ? "L" : "S" });
      // mark the faded extreme (pullback origin) with a hollow diamond + the pullback distance
      const ext = extremeForEntry(w.frames, fi);
      if (ext) {
        markers.push({ time: toTs(ext.frame.time),
          position: isLong ? "belowBar" : "aboveBar",
          color: "#8b949e", shape: "square",
          text: `${Math.round(ext.pullbackPts)}pt` });
      }
    }
    // Exit: gold circle. When a trade closes AND reverses on the same bar, an entry arrow lands on
    // this bar too -- put the exit circle on the OPPOSITE side from that entry arrow so it isn't
    // buried. Otherwise use the far side of the bar from where price closed.
    if (f.exit_reason) {
      const pos = f.entry_dir === 1 ? "aboveBar"          // entry arrow is belowBar -> exit above
                : f.entry_dir === -1 ? "belowBar"         // entry arrow is aboveBar -> exit below
                : (f.pos === 0 ? "aboveBar" : "belowBar");
      markers.push({ time: t, position: pos, color: "#d29922", shape: "circle",
        text: "● " + f.exit_reason[0].toUpperCase(), size: 2 });
    }
    if (f.pos !== 0 && f.stop_level != null && f.i <= state.cur) stopL.push({ time: t, value: f.stop_level });
  }
  // lightweight-charts requires markers sorted by time asc; the extreme marker sits before its
  // entry, so re-sort before setting.
  markers.sort((a, b) => a.time - b.time);
  candle.setMarkers(markers);
  stopSeries.setData(stopL);
}

// ---- panels ----
function curFrame() {
  const w = state.win; if (!w) return null;
  const k = state.cur - w.lo;
  return (k >= 0 && k < w.frames.length) ? w.frames[k] : null;
}
// the trade whose [entry_i, exit_i] contains bar idx (or null)
function tradeAt(idx) {
  for (const t of state.trades) if (idx >= t.entry_i && idx <= t.exit_i) return t;
  return null;
}
// frame lookup by absolute bar index within the loaded window
function frameAt(idx) {
  const w = state.win; if (!w) return null;
  const k = idx - w.lo;
  return (k >= 0 && k < w.frames.length) ? w.frames[k] : null;
}
function renderState(frame) {
  const f = frame || curFrame(); if (!f) return;
  const posTxt = f.pos > 0 ? "LONG" : f.pos < 0 ? "SHORT" : "flat";
  const posCls = f.pos > 0 ? "long" : f.pos < 0 ? "short" : "";
  const unreal = f.unreal_usd;
  const at = tradeAt(f.i);      // the trade active on this bar (for its full MFE/MAE)
  // Per-strategy label for the `run` frame column (OLS run for slope, displacement for WDF, ...).
  const strat = (state.meta.cfg && state.meta.cfg.strategy) || "";
  const runLabel = strat === "window_displacement_fade" ? "displacement" : "OLS run";
  // res/supp are the generic "two horizontal levels" channel: OR-high/low for ORB, the two drive
  // trigger rails for open-drive, S/R lines otherwise.
  const isORB = strat === "opening_range_breakout";
  const isOD = strat === "open_drive";
  const hiLbl = isORB ? "OR high" : isOD ? "drive-up lvl" : "resistance";
  const loLbl = isORB ? "OR low" : isOD ? "drive-dn lvl" : "support";
  const rows = [
    ["time", ldnFull(f.time)],
    ["bar #", f.i],
    ["close", fmt(f.c)],
    // S/R and R² only make sense for strategies that populate them -- hide when null.
    ...(f.res != null ? [[hiLbl, fmt(f.res)]] : []),
    ...(f.supp != null ? [[loLbl, fmt(f.supp)]] : []),
    ...(f.anchor != null ? [["RTH open", fmt(f.anchor)]] : []),
    ...(f.run != null ? [[runLabel, `${fmt(f.run, 1)} pt`]] : []),
    ...(f.r2 != null ? [["OLS R²", fmt(f.r2, 3)]] : []),
    ["position", `<span class="${posCls}">${posTxt}</span>`],
    ["entry px", fmt(f.entry_px)],
    ["stop", f.stop_level != null ? `${fmt(f.stop_level)} (${f.stop_kind})` : "—"],
    ["unrealized", unreal != null ? `<span class="${unreal >= 0 ? "pos" : "neg"}">$${fmt(unreal, 1)}</span>` : "—"],
    ["trade MFE", at ? `<span class="pos">${fmt(at.mfe, 1)} pt</span>` : "—"],
    ["trade MAE", at ? `<span class="neg">${fmt(at.mae, 1)} pt</span>` : "—"],
    ["realized cum", `<span class="${f.cum_usd >= 0 ? "pos" : "neg"}">$${fmt(f.cum_usd, 1)}</span>`],
  ];
  $("stateBody").innerHTML = rows.map(([k, v]) => `<div class="k">${k}</div><div class="v">${v}</div>`).join("");
}
// Pretty labels for known cfg keys (any strategy's). Unknown keys are humanized automatically,
// so a new strategy's params show up with no code change -- the panel is driven by the run's cfg.
const PARAM_LABELS = {
  strategy: "strategy",
  win_len: "window (bars)", thr: "displacement thr", tp: "take-profit (pt)", sl: "stop-loss (pt)",
  prev_block: "prev filter on", prev_win: "prev window (bars)", prev_thr: "prev reverse >(pt)",
  block_after_tp: "block after TP", min_r2: "min R²",
  // slope-touch-fade keys (kept so its runs still read well):
  run_min: "min run (pt)", pullback: "pullback (pt)", break_tol: "break tol", sr_half: "S/R half",
  enable_trail: "trail on", trail: "trail (pt)", enable_init: "init stop on", stop_buf: "stop buf",
  block_ny: "block NY", block_ln: "block LN", mult: "$/pt",
};
const humanize = (k) => k.replace(/_/g, " ");
const fmtParam = (v) =>
  v === true ? "true" : v === false ? "false" : (v == null ? "—" : v);
function renderParams() {
  const cfg = state.meta.cfg || {};
  // Render EVERY key present in the run's cfg, in its own order; strategy name first if present.
  const keys = Object.keys(cfg);
  keys.sort((a, b) => (a === "strategy" ? -1 : b === "strategy" ? 1 : 0));
  $("paramsBody").innerHTML = keys.map((k) =>
    `<div class="k">${PARAM_LABELS[k] || humanize(k)}</div><div class="v">${fmtParam(cfg[k])}</div>`
  ).join("");
}
function renderSummary() {
  const s = state.meta.stats;
  $("summary").innerHTML =
    `<span>trades</span> <b>${s.n}</b>` +
    `<span>net</span> <b class="${s.usd >= 0 ? "" : ""}">$${fmt(s.usd, 0)}</b>` +
    `<span>win%</span> <b>${fmt(s.wr, 1)}</b>` +
    `<span>PF</span> <b>${fmt(s.pf, 2)}</b>`;
  const ex = state.meta.exact;
  const b = $("fidelity");
  b.textContent = ex ? "exact" : "recomputed";
  b.className = "badge " + (ex ? "exact" : "recomputed");
  b.title = ex ? "Ran on a CSV with Pine's exact S/R + OLS columns — bar-exact."
               : "Ran on a raw CSV — S/R & OLS recomputed, directionally faithful.";
}
// a trade is "in view" if any part of it overlaps the active filter window [viewLo, viewHi)
const tradeInView = (t) => t.exit_i >= state.viewLo && t.entry_i < state.viewHi;
function renderTrades() {
  const tb = $("tradeTable").querySelector("tbody");
  // keep the ORIGINAL index k on each row (for click-seek + highlight), but only render in-view rows
  const rows = state.trades
    .map((t, k) => ({ t, k }))
    .filter(({ t }) => tradeInView(t));
  const total = state.trades.length;
  $("tradeCount").textContent = rows.length === total
    ? `(${total})` : `(${rows.length} of ${total} in view)`;
  tb.innerHTML = rows.map(({ t, k }) => {
    const dc = t.dir > 0 ? "long" : "short";
    const pc = t.pts >= 0 ? "pos" : "neg";
    return `<tr data-k="${k}">
      <td>${k + 1}</td>
      <td class="${dc}">${t.dir > 0 ? "L" : "S"}</td>
      <td>${ldnShort(t.entry_time)}</td>
      <td>${ldnShort(t.exit_time)}</td>
      <td class="${pc}">${fmt(t.pts, 1)}</td>
      <td class="pos">${fmt(t.mfe, 0)}</td>
      <td class="neg">${fmt(t.mae, 0)}</td>
      <td>${t.reason}</td>
      <td class="${t.cum_usd >= 0 ? "pos" : "neg"}">${fmt(t.cum_usd, 0)}</td>
    </tr>`;
  }).join("");
  tb.querySelectorAll("tr").forEach((tr) =>
    tr.onclick = () => seekTo(state.trades[+tr.dataset.k].entry_i));
}
function highlightActiveTrade() {
  // active = the trade whose [entry_i, exit_i] contains cur
  let a = -1;
  for (let k = 0; k < state.trades.length; k++) {
    const t = state.trades[k];
    if (state.cur >= t.entry_i && state.cur <= t.exit_i) { a = k; break; }
  }
  if (a === state.activeTrade) return;
  state.activeTrade = a;
  const rows = $("tradeTable").querySelectorAll("tbody tr");
  rows.forEach((tr) => tr.classList.toggle("active", +tr.dataset.k === a));
  if (a >= 0) rows[a]?.scrollIntoView({ block: "nearest" });
}

// ---- playhead + scrub ----
function updateScrubLabel() {
  const f = curFrame();
  const span = state.viewHi - state.viewLo;
  const rel = state.cur - state.viewLo;
  const pct = span > 1 ? (rel / (span - 1) * 100).toFixed(1) : 0;
  $("scrubLabel").textContent = f
    ? `${ldnMin(f.time)}   bar ${state.cur}  (${pct}% of view)`
    : `bar ${state.cur}`;
}
async function refreshAll() {
  await ensureWindow(state.cur);
  drawMarkersAndStop();
  renderState(); updateScrubLabel(); highlightActiveTrade();
  $("scrub").value = state.cur;
}
async function seekTo(idx) {
  state.cur = clampView(idx);                 // confine the playhead to the active filter window
  await refreshAll();
  recenter();
}
// Keep the playhead near the right using LOGICAL (bar-offset) ranges. Always show a full VIEW_BARS
// width (clamped to the loaded window) so the view never collapses to a few bars at the edges.
const VIEW_BARS = 240;
function recenter() {
  const w = state.win; if (!w) return;
  const n = w.frames.length;
  const k = state.cur - w.lo;                 // playhead offset within the window array
  let to = Math.min(n, k + 6);                 // small headroom to the right of the playhead
  let from = to - VIEW_BARS;
  if (from < 0) { from = 0; to = Math.min(n, VIEW_BARS); }  // at the start: fill from the left
  chart.timeScale().setVisibleLogicalRange({ from, to });
}

// ---- replay loop ----
// Async self-scheduling loop: each step advances `speed` bars, awaits the (possibly windowed)
// render, then schedules the next step ~16ms later. Awaiting each step means it can never outrun
// data fetches or pile up rejected promises -- if seekTo throws, the loop stops cleanly.
async function replayLoop() {
  const last = state.viewHi - 1;              // stop at the end of the active filter window
  while (state.playing) {
    const advance = Math.max(1, Math.round(state.speed));
    let next = Math.min(last, state.cur + advance);
    try { await seekTo(next); }
    catch (e) { console.error("replay step failed", e); pause(); return; }
    if (state.cur >= last) { pause(); return; }   // reached the end of the view
    await new Promise((r) => setTimeout(r, 16));
  }
}
function play() {
  if (state.playing) return;
  if (state.cur >= state.viewHi - 1) state.cur = state.viewLo;   // rewind to view start
  state.playing = true;
  $("btnPlay").classList.add("playing"); $("btnPlay").textContent = "⏸";
  replayLoop();
}
function pause() {
  state.playing = false;
  $("btnPlay").classList.remove("playing"); $("btnPlay").textContent = "▶";
}

// ---- run loading ----
async function loadRun(tag) {
  showLoading(true);
  state.tag = tag; state.playing = false; state.win = null; state.activeTrade = -1;
  const d = await api(`/run/${tag}`);
  state.meta = d.meta; state.trades = d.trades; state.nBars = d.n_bars; state.cur = 0;
  renderSummary(); renderParams();   // renderTrades() is driven by setView (needs the view window)
  // load the navigation index and default to the FIRST month (per the requested default filter)
  state.index = await api(`/run/${tag}/index`);
  populateFilters();
  state.filterMode = "month";
  syncFilterUI();
  applyFilterFromControls();     // sets viewLo/viewHi + seeks to view start
  showLoading(false);
}

// ---- filters ----
function populateFilters() {
  const ix = state.index;
  $("monthSelect").innerHTML = ix.months
    .map((m) => `<option value="${m.lo_i}|${m.hi_i}">${m.key}</option>`).join("");
  $("contractSelect").innerHTML = ix.contracts
    .map((c) => `<option value="${c.lo_i}|${c.hi_i}">${c.symbol} · ${c.start.slice(0, 10)}→${c.end.slice(0, 10)}${c.approx ? "  (approx)" : ""}</option>`).join("");
  // default the date-range inputs to the run span
  $("rangeStart").value = ix.span.start.slice(0, 10);
  $("rangeEnd").value = ix.span.end.slice(0, 10);
  $("rangeStart").min = $("rangeEnd").min = ix.span.start.slice(0, 10);
  $("rangeStart").max = $("rangeEnd").max = ix.span.end.slice(0, 10);
}
function syncFilterUI() {
  document.querySelectorAll("#filterMode button").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === state.filterMode));
  $("monthSelect").classList.toggle("hidden", state.filterMode !== "month");
  $("rangeCtl").classList.toggle("hidden", state.filterMode !== "range");
  $("contractSelect").classList.toggle("hidden", state.filterMode !== "contract");
}
// set the active view window and jump the playhead to its start
async function setView(lo, hi) {
  state.viewLo = Math.max(0, lo);
  state.viewHi = Math.min(state.nBars, hi);
  state.win = null;                               // force a fresh frame fetch for the new region
  $("scrub").min = state.viewLo;
  $("scrub").max = state.viewHi - 1;
  state.activeTrade = -1;                          // force highlight recompute for the new view
  renderTrades();                                  // refilter the table to the new window
  await seekTo(state.viewLo);
}
function parseLoHi(v) { const [a, b] = v.split("|").map(Number); return [a, b]; }
async function applyFilterFromControls() {
  pause();
  if (state.filterMode === "month") {
    await setView(...parseLoHi($("monthSelect").value));
  } else if (state.filterMode === "contract") {
    await setView(...parseLoHi($("contractSelect").value));
  } else {  // range: map the two dates to bar indices via the backend
    const s = $("rangeStart").value, e = $("rangeEnd").value;
    const d = await api(`/run/${state.tag}/frames?start=${s}&end=${e}&cols=i`);
    if (d.n === 0) { alert("no bars in that date range"); return; }
    await setView(d.lo, d.hi);
  }
}

// ---- New Run modal: build the param form from /params/{strategy}, POST /simulate, poll, load ----
async function apiPost(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}
const newrun = { schema: null };

async function openNewRun() {
  const strats = await api("/strategies");
  const mS = $("mStrategy");
  mS.innerHTML = strats.map(s => `<option value="${s.strategy}">${s.label}</option>`).join("");
  mS.onchange = () => buildParamForm(mS.value);
  await buildParamForm(mS.value);
  $("mStatus").textContent = ""; $("mStatus").className = "mstatus";
  $("newRunModal").classList.remove("hidden");
}
function closeNewRun() { $("newRunModal").classList.add("hidden"); }

async function buildParamForm(strategy) {
  const schema = await api(`/params/${strategy}`);
  newrun.schema = schema;
  const groups = {};
  for (const f of schema.params) (groups[f.group] = groups[f.group] || []).push(f);
  let html = "";
  for (const [g, fields] of Object.entries(groups)) {
    html += `<div class="mgroup">${g}</div>`;
    for (const f of fields) {
      const id = `mp_${f.name}`;
      if (f.type === "bool") {
        html += `<div class="mfield"><label for="${id}">${f.label}</label>` +
          `<input type="checkbox" id="${id}" ${f.default ? "checked" : ""}></div>`;
      } else {
        const step = f.step != null ? f.step : (f.type === "int" ? 1 : "any");
        const mn = f.min != null ? `min="${f.min}"` : "";
        const mx = f.max != null ? `max="${f.max}"` : "";
        html += `<div class="mfield"><label for="${id}">${f.label}</label>` +
          `<input type="number" id="${id}" value="${f.default}" step="${step}" ${mn} ${mx}></div>`;
      }
    }
  }
  $("mParams").innerHTML = html;
}

function collectParams() {
  const out = {};
  for (const f of newrun.schema.params) {
    const el = $(`mp_${f.name}`);
    if (f.type === "bool") out[f.name] = el.checked;
    else out[f.name] = f.type === "int" ? parseInt(el.value, 10) : parseFloat(el.value);
  }
  return out;
}

async function generateRun() {
  const btn = $("btnGenerate"), st = $("mStatus");
  const body = {
    strategy: $("mStrategy").value,
    dataset: $("mDataset").value,
    start: $("mStart").value || null,   // <input type=month> gives "YYYY-MM"
    end: $("mEnd").value || null,
    params: collectParams(),
  };
  btn.disabled = true; st.className = "mstatus"; st.textContent = "generating… (first run warms up ~10s)";
  try {
    let res = await apiPost("/simulate", body);
    if (res.state !== "done") {
      // poll the job
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 700));
        const j = await api(`/job/${res.job_id}`);
        if (j.state === "done") { res = { ...res, ...j }; break; }
        if (j.state === "error") throw new Error(j.error || "simulation failed");
        st.textContent = `generating… (${j.state})`;
      }
    }
    if (res.state !== "done" && !res.tag) throw new Error("timed out");
    st.textContent = res.cached ? "loaded existing run" : "done";
    await refreshRunsAndLoad(res.tag);
    closeNewRun();
  } catch (e) {
    st.className = "mstatus err"; st.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

async function refreshRunsAndLoad(tag) {
  const runs = (await api("/runs")).filter(r => !r.error).sort((a, b) => a.n_bars - b.n_bars);
  const sel = $("runSelect");
  sel.innerHTML = runs
    .map(r => `<option value="${r.tag}">${r.tag} · ${r.n_trades} trades · $${fmt(r.stats?.usd, 0)}</option>`).join("");
  sel.value = tag;
  await loadRun(tag);
}

// ---- wiring ----
async function init() {
  const runs = (await api("/runs")).filter(r => !r.error)
    .sort((a, b) => a.n_bars - b.n_bars);   // smallest run first => instant first paint
  const sel = $("runSelect");
  sel.innerHTML = runs
    .map(r => `<option value="${r.tag}">${r.tag} · ${r.n_trades} trades · $${fmt(r.stats?.usd, 0)}</option>`).join("");
  sel.onchange = () => loadRun(sel.value);

  // New Run modal wiring
  $("btnNewRun").onclick = () => openNewRun().catch(e => alert("open failed: " + e.message));
  $("btnCloseModal").onclick = closeNewRun;
  $("btnGenerate").onclick = generateRun;
  $("newRunModal").onclick = (e) => { if (e.target.id === "newRunModal") closeNewRun(); };

  $("btnPlay").onclick = () => state.playing ? pause() : play();
  $("btnStepFwd").onclick = () => { pause(); seekTo(state.cur + 1); };
  $("btnStepBack").onclick = () => { pause(); seekTo(state.cur - 1); };
  $("btnFirst").onclick = () => { pause(); seekTo(state.viewLo); };
  $("btnLast").onclick = () => { pause(); seekTo(state.viewHi - 1); };
  // trade nav confined to the active view
  $("btnNextTrade").onclick = () => { pause(); const t = state.trades.find(t => t.entry_i > state.cur && t.entry_i < state.viewHi); if (t) seekTo(t.entry_i); };
  $("btnPrevTrade").onclick = () => { pause(); const prev = [...state.trades].reverse().find(t => t.entry_i < state.cur && t.entry_i >= state.viewLo); if (prev) seekTo(prev.entry_i); };
  $("speed").onchange = (e) => state.speed = +e.target.value;
  $("winLen").onchange = (e) => { state.winLen = +e.target.value; state.win = null; seekTo(state.cur); };
  $("scrub").oninput = (e) => { pause(); seekTo(+e.target.value); };

  // filter mode toggle + controls. Month/Contract apply immediately (they carry a valid selection);
  // Date range waits for the Apply button so switching to it doesn't reload the whole span first.
  document.querySelectorAll("#filterMode button").forEach((b) =>
    b.onclick = () => {
      state.filterMode = b.dataset.mode; syncFilterUI();
      if (state.filterMode !== "range") applyFilterFromControls();
    });
  $("monthSelect").onchange = () => applyFilterFromControls();
  $("contractSelect").onchange = () => applyFilterFromControls();
  $("rangeApply").onclick = () => applyFilterFromControls();

  if (sel.value) await loadRun(sel.value);
}
// Wait until the container has a real size (flex layout done), then create the chart and load.
function boot() {
  const el = $("chart");
  if (el.clientWidth < 50 || el.clientHeight < 50) { requestAnimationFrame(boot); return; }
  createChart();
  init().catch((e) => { showLoading(false); alert("init failed: " + e.message); console.error(e); });
}
requestAnimationFrame(boot);
