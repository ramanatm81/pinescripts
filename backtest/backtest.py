#!/usr/bin/env python3
"""
Faithful Python port of slope_strategy.pine for offline parameter sweeps.
Replays 1m OHLC bar-by-bar reproducing the Pine state machine.

Order-fill model (matches TradingView strategy semantics with the script's
own intrabar hard-SL / trail handling):
  - Entries fill at close of the signal bar (script sets entryPrice := close).
  - The script manages hard SL and trailing itself on subsequent bars using
    that bar's high/low, and closes via strategy.close (fills at bar close in
    backtest unless stop pins). We replicate: SL hit -> fill at the SL price
    (stop=_slPrice pins fill, no gap slippage, per the script comment). TP via
    strategy.exit limit -> fill at TP price. TRAIL/TEXP/THRD -> fill at close.
"""
import csv, math
from datetime import datetime, timezone, timedelta

DATA = "/Users/maheshk81/Downloads/data.csv"

def load():
    bars = []
    with open(DATA) as f:
        for row in csv.DictReader(f):
            t = row["time"]
            try:
                o = float(row["open"]); h = float(row["high"])
                l = float(row["low"]); c = float(row["close"])
            except (ValueError, TypeError):
                continue
            # parse CT minutes from ISO ts like 2026-06-07T17:00:00-05:00
            if not t:
                # row with blank time: skip (can't place in session) — these are tail rows
                continue
            dt = datetime.fromisoformat(t)  # tz-aware (offset varies: -05:00 old, +01:00 new)
            # Pine uses hour(time,"America/Chicago"); normalize to Chicago (CDT = UTC-5 in
            # this Jun/Jul window) regardless of the CSV's stamp offset.
            ct = dt.astimezone(timezone(timedelta(hours=-5)))
            ctmins = ct.hour*60 + ct.minute
            bars.append((ct, o, h, l, c, ctmins))
    return bars

POINT_VALUE = 1.0  # PnL reported in points; * contract value externally if needed

def run(bars, p):
    # --- params (dict p) with defaults matching the pine inputs ---
    # Optional per-bar entry block (VWAP-zone proximity filter etc.): a list/array the same
    # length as bars; when vwap_block[bi] is truthy, NEW normal entries are suppressed on
    # that bar (open-trade management unaffected). None = no filter.
    vwap_block      = p.get("vwap_block", None)
    # Extreme-slope SL override: when abs(entry slope) >= extremeSlope, use extremeSL pts
    # instead of the SMA-based 50/30 (strong momentum needs room). 0/None = off.
    extremeSlope    = p.get("extremeSlope", 0.0) or 0.0
    extremeSL       = p.get("extremeSL", 0.0) or 0.0
    # Delayed entry for extreme-slope ABOVE-SMA signals: when close>SMA and |slope|>=
    # delayExtremeSlope at a would-be entry, DON'T enter now — wait delayBars, then enter
    # same direction ONLY IF the slope signal is still valid (same side, beyond slopeEntry).
    # 0 = off.
    delayExtremeSlope = p.get("delayExtremeSlope", 0.0) or 0.0
    delayBars         = p.get("delayBars", 0) or 0
    # Big-loss-above-SMA block: after a loss >= bigLossPts taken while close>SMA, block
    # ALL new entries (both directions) for bigLossCool bars. 0 = off.
    bigLossPts        = p.get("bigLossPts", 0.0) or 0.0
    bigLossCool       = p.get("bigLossCool", 0) or 0
    # Break-even stop: once the trade runs beArm pts in our favor (peak), move the stop to
    # entry + beOffset so the trade can no longer become a loss. 0 = off.
    beArm             = p.get("beArm", 0.0) or 0.0
    beOffset          = p.get("beOffset", 0.0) or 0.0
    lookback        = p.get("lookback", 10)
    slopeEntry      = p["slopeEntry"]
    angleEntry      = p.get("angleEntry", False)
    angleThresh     = p.get("angleThresh", 9.5)
    angleAtrLen     = p.get("angleAtrLen", 14)
    calmSkipMult    = p.get("calmSkipMult", 0.0)
    atrLongLen      = p.get("atrLongLen", 100)
    slPts           = p.get("slPts", 50.0)
    enableSmaSL     = p.get("enableSmaSL", True)
    smaPeriod       = p.get("smaPeriod", 9)
    slAboveSma      = p["slAboveSma"]
    slBelowSma      = p["slBelowSma"]
    tpPts           = p["tpPts"]
    tpMult          = p["tpMult"]
    trailTrigger    = p["trailTrigger"]
    trailDist       = p["trailDist"]
    trailDistStrong = p["trailDistStrong"]
    enableTExp      = p.get("enableTExp", True)
    tExpBars        = p["tExpBars"]
    enableTExpHard  = p.get("enableTExpHard", True)
    tExpHardBars    = p["tExpHardBars"]
    tExpHardSlope   = p["tExpHardSlope"]
    enableThrdRev   = p.get("enableThrdReversal", True)
    enableDeepBlock = p.get("enableDeepBlock", False)
    dojiPct         = p.get("dojiPct", 10.0)
    cooldownBars    = p.get("cooldownBars", 10)
    cooldownBarsRTH = p.get("cooldownBarsRTH", 10)
    deepSlope       = p.get("deepSlope", 3.0)
    enableDeepLossOpp = p.get("enableDeepLossOppBlock", False)
    enableBodyFilter= p.get("enableBodyFilter", False)
    minBodyPts      = p.get("minBodyPts", 10.0)
    enableSRFilter  = p.get("enableSRFilter", True)
    srHalfWidth     = p.get("srHalfWidth", 10)
    srZoneWidth     = p.get("srZoneWidth", 25.0)
    srLookback      = p.get("srLookback", 0)
    enableDrought   = p.get("enableDroughtBlock", False)
    droughtBars     = p.get("droughtBlockBars", 50)
    blockNYOpen     = p.get("blockNYOpen", False)
    blockLNOpen     = p.get("blockLNOpen", True)
    blockPreNY      = p.get("blockPreNY", True)
    # breach-fade override (experimental). Requires smoothed S/R (smoothSRPct).
    enableBreachFade= p.get("enableBreachFade", False)
    breachFadeBars  = p.get("breachFadeBars", 5)
    smoothSRPct     = p.get("smoothSRPct", 0.30)
    breachFadeSL    = p.get("breachFadeSL", True)   # True = manage like normal (SMA stop + TP); False = no SL, exit only on opposite signal

    # --- state ---
    inTrade=False; tradeDir=0; entryPrice=None; entrySlope=None
    bestPrice=None; trailStop=None; cooldown=0; barsInTrade=0; activeSL=None
    delayPending=0; delayDir=0   # delayed extreme-above-SMA entry: bars left, direction
    bigLossBlock=0               # bars left of the all-directions block after a big loss above SMA
    beArmed=False                # break-even stop armed (trade ran beArm favorable)
    slExitDir=0; slEntryPrice=None; barrierBuf=None; barrierCool=0; slBarrier=None
    thrdRevPending=False; thrdRevDir=0
    deepBestPrice=None; deepBlockDir=0; entryWasDeep=False; exitBestPrice=None
    deepLossBlockDir=0

    slopeBuf=[]; legSlope=None; legSlopeAngle=None
    trBuf=[]; atrVal=None; prevClose=None
    trBufLong=[]; atrLong=None
    closes=[]; highs=[]; lows=[]
    lastFractalHigh=None; lastFractalLow=None
    lastFractalHighBar=None; lastFractalLowBar=None
    # breach-fade state
    smHigh=None; smLow=None
    barsSinceSup=None; barsSinceRes=None
    breachTradeDir=0

    trades=[]  # (dir, entry, exit, pnl_pts, reason, deep)
    pos_size_prev=0  # for posClosed detection not needed; we track inline

    def sma(period):
        if len(closes) < period: return None
        return sum(closes[-period:]) / period

    for bi,(dt,o,h,l,c,ctmins) in enumerate(bars):
        inRTH = 510 <= ctmins < 900
        eodClose = 900 <= ctmins < 960
        activeCooldown = cooldownBarsRTH if inRTH else cooldownBars
        nyOpenBlock = blockNYOpen and 510 <= ctmins < 540
        lnOpenBlock = blockLNOpen and 120 <= ctmins < 150
        preNYBlock  = blockPreNY  and 450 <= ctmins < 540
        ethOpenBlock= 1020 <= ctmins < 1050

        closes.append(c); highs.append(h); lows.append(l)
        smaVal = sma(smaPeriod)

        rng = h-l
        bodyPct = (abs(c-o)/rng*100.0) if rng>0 else 0.0
        isDoji = bodyPct < dojiPct

        # ---- fractal pivots (confirmed srHalfWidth bars after pivot bar) ----
        # pivot high at index bi-srHalfWidth if it's the max high of window [bi-2w .. bi]
        w = srHalfWidth
        if bi >= 2*w:
            center = bi - w
            ch = highs[center]
            if ch == max(highs[bi-2*w:bi+1]) and ch >= ch:  # strict-enough; ties ok like pine ==max approx
                # pine uses ta.pivothigh which requires strict greater on both sides; approximate with max & uniqueness
                left = highs[bi-2*w:center]; right = highs[center+1:bi+1]
                if all(ch > x for x in left) and all(ch > x for x in right):
                    lastFractalHigh = ch; lastFractalHighBar = center
            cl = lows[center]
            left = lows[bi-2*w:center]; right = lows[center+1:bi+1]
            if all(cl < x for x in left) and all(cl < x for x in right):
                lastFractalLow = cl; lastFractalLowBar = center
            # smoothed S/R: hold flat until a new pivot differs by >= smoothSRPct% of price
            if enableBreachFade:
                _isPH = (lastFractalHighBar == center)
                _isPL = (lastFractalLowBar == center)
                if _isPH:
                    _thr = smoothSRPct/100.0*c
                    smHigh = ch if (smHigh is None or abs(ch-smHigh) >= _thr) else smHigh
                if _isPL:
                    _thr = smoothSRPct/100.0*c
                    smLow = cl if (smLow is None or abs(cl-smLow) >= _thr) else smLow

        # breach counters vs smoothed levels (only tracked when breach-fade is on)
        if enableBreachFade:
            if smLow is not None and l < smLow: barsSinceSup = 0
            elif barsSinceSup is not None: barsSinceSup += 1
            if smHigh is not None and h > smHigh: barsSinceRes = 0
            elif barsSinceRes is not None: barsSinceRes += 1

        def valid_high():
            if lastFractalHigh is None: return False
            if srLookback==0: return True
            return (bi-lastFractalHighBar) <= srLookback
        def valid_low():
            if lastFractalLow is None: return False
            if srLookback==0: return True
            return (bi-lastFractalLowBar) <= srLookback
        nearHigh = valid_high() and abs(c-lastFractalHigh) <= srZoneWidth
        nearLow  = valid_low()  and abs(c-lastFractalLow)  <= srZoneWidth
        srBlock = enableSRFilter and (nearHigh or nearLow)

        # drought
        lastAny = None
        if lastFractalHighBar is not None and lastFractalLowBar is not None:
            lastAny = max(lastFractalHighBar,lastFractalLowBar)
        elif lastFractalHighBar is not None: lastAny=lastFractalHighBar
        elif lastFractalLowBar is not None: lastAny=lastFractalLowBar
        barsSinceFractal = bi if lastAny is None else bi-lastAny
        inFractalDrought = enableDrought and barsSinceFractal >= droughtBars

        # ---- rolling slope ----
        legSlope = None
        if not eodClose and not isDoji:
            slopeBuf.append(c)
            if len(slopeBuf) > lookback: slopeBuf.pop(0)
        if len(slopeBuf) == lookback:
            n=lookback; sx=sy=sxy=sx2=0.0
            for i in range(n):
                x=float(i); y=slopeBuf[i]
                sx+=x; sy+=y; sxy+=x*y; sx2+=x*x
            denom=n*sx2-sx*sx
            legSlope = round((n*sxy-sx*sy)/denom,2) if denom!=0 else 0.0

        tr = (h-l) if prevClose is None else max(h-l, abs(h-prevClose), abs(l-prevClose))
        prevClose = c
        trBuf.append(tr)
        if len(trBuf) > angleAtrLen: trBuf.pop(0)
        atrVal = (sum(trBuf)/len(trBuf)) if len(trBuf)==angleAtrLen else None
        trBufLong.append(tr)
        if len(trBufLong) > atrLongLen: trBufLong.pop(0)
        atrLong = (sum(trBufLong)/len(trBufLong)) if len(trBufLong)==atrLongLen else None
        legSlopeAngle = None
        if legSlope is not None and atrVal is not None and atrVal>0:
            legSlopeAngle = round(math.degrees(math.atan(legSlope/atrVal)),1)

        def close_trade(exit_price, reason):
            nonlocal deepLossBlockDir, deepBlockDir, deepBestPrice, bigLossBlock, beArmed
            beArmed=False
            pnl = (exit_price-entryPrice) if tradeDir==1 else (entryPrice-exit_price)
            wasLong = (tradeDir==1)
            trades.append((tradeDir, entryPrice, exit_price, pnl, reason, entryWasDeep, dt))
            # pine posClosed bookkeeping: deep profit block / deep loss block
            if enableDeepBlock and entryWasDeep and pnl>0:
                deepBlockDir = 1 if wasLong else -1
                deepBestPrice = exitBestPrice
            if entryWasDeep and pnl<=0:
                deepLossBlockDir = 1 if wasLong else -1
            # big-loss-above-SMA: block ALL new entries for bigLossCool bars
            if bigLossPts>0 and bigLossCool>0 and pnl <= -bigLossPts \
               and smaVal is not None and c > smaVal:
                bigLossBlock = bigLossCool

        # ===== session block exits =====
        inAnyBlock = nyOpenBlock or lnOpenBlock or preNYBlock or ethOpenBlock
        if inAnyBlock and inTrade:
            close_trade(c, "BLK")
            tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; barsInTrade=0; cooldown=0

        # ===== EOD reset =====
        if eodClose and inTrade:
            close_trade(c, "EOD")
        if eodClose:
            tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; cooldown=0; barsInTrade=0
            slExitDir=0; slBarrier=None; slEntryPrice=None; barrierBuf=None; barrierCool=0
            deepLossBlockDir=0

        # ===== cooldown countdown =====
        if cooldown>0 and not inTrade: cooldown-=1
        if bigLossBlock>0 and not inTrade: bigLossBlock-=1

        # ===== slExitDir barrier clear =====
        if slExitDir!=0 and not inTrade:
            if slEntryPrice is None or barrierBuf is None:
                slExitDir=0; slEntryPrice=None; barrierBuf=None
            elif slExitDir==1:
                if c > slEntryPrice+barrierBuf: slExitDir=0; slEntryPrice=None; barrierBuf=None
            else:
                if c < slEntryPrice-barrierBuf: slExitDir=0; slEntryPrice=None; barrierBuf=None

        # ===== break-even stop (checked BEFORE hard SL; once armed, the trade can't lose) =====
        # Arm when peak favorable >= beArm; then exit at entry+beOffset (long) / entry-beOffset (short).
        if inTrade and beArm>0:
            favPeak = (h-entryPrice) if tradeDir==1 else (entryPrice-l)
            if favPeak >= beArm:
                beArmed=True
            if beArmed:
                beStop = entryPrice+beOffset if tradeDir==1 else entryPrice-beOffset
                beHit  = (tradeDir==1 and l <= beStop) or (tradeDir==-1 and h >= beStop)
                if beHit:
                    close_trade(beStop, "BE")
                    tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; cooldown=activeCooldown; beArmed=False

        # ===== hard SL =====
        if inTrade:
            hardSLHit = (tradeDir==1 and l <= entryPrice-activeSL) or (tradeDir==-1 and h >= entryPrice+activeSL)
            if hardSLHit:
                fill = entryPrice-activeSL if tradeDir==1 else entryPrice+activeSL
                close_trade(fill, "SL")
                slExitDir=tradeDir; slEntryPrice=entryPrice; barrierBuf=activeSL; barrierCool=0
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; cooldown=activeCooldown; beArmed=False

        # ===== TP check (limit) — strategy.exit limit fills if price reaches TP =====
        # Pine's strategy.exit handles both stop and limit on the same bar; we already
        # did SL above. Now TP:
        if inTrade:
            tp = entryPrice + tpPts*tpMult if tradeDir==1 else entryPrice - tpPts*tpMult
            tpHit = (tradeDir==1 and h>=tp) or (tradeDir==-1 and l<=tp)
            if tpHit:
                close_trade(tp, "TP")
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; cooldown=activeCooldown; barsInTrade=0

        # ===== bar counter + time expiry =====
        if inTrade: barsInTrade+=1
        else: barsInTrade=0

        # if a breach trade was just closed by SL/TP/session/EOD above, clear its flag
        if breachTradeDir!=0 and not inTrade:
            breachTradeDir=0

        # breach trades: exit on OPPOSITE slope signal (in addition to the SL/TP above).
        # SL/TP already ran, so this only fires if neither hit. Then skip TEXP/THRD/trail.
        if enableBreachFade and inTrade and breachTradeDir!=0 and legSlope is not None:
            oppLong  = legSlope < -slopeEntry
            oppShort = legSlope >  slopeEntry
            if (breachTradeDir==-1 and oppLong) or (breachTradeDir==1 and oppShort):
                close_trade(c,"BF")
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; barsInTrade=0; cooldown=0
                breachTradeDir=0

        if enableTExp and inTrade and breachTradeDir==0 and barsInTrade>=tExpBars:
            isProfit = (tradeDir==1 and c>entryPrice) or (tradeDir==-1 and c<entryPrice)
            if isProfit:
                close_trade(c,"TEXP")
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; barsInTrade=0; cooldown=activeCooldown

        if enableTExpHard and inTrade and breachTradeDir==0 and barsInTrade>=tExpHardBars and legSlope is not None:
            slopeAgainst = (tradeDir==1 and legSlope<=-tExpHardSlope) or (tradeDir==-1 and legSlope>=tExpHardSlope)
            if slopeAgainst:
                thrdIsLoss = (tradeDir==1 and c<entryPrice) or (tradeDir==-1 and c>entryPrice)
                close_trade(c,"THRD")
                if thrdIsLoss:
                    slExitDir=tradeDir; slEntryPrice=entryPrice; barrierBuf=activeSL; barrierCool=0
                if enableThrdRev:
                    thrdRevPending=True; thrdRevDir=-tradeDir; cooldown=2
                else:
                    cooldown=activeCooldown
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; barsInTrade=0

        # ===== THRD reversal entry =====
        if thrdRevPending and not inTrade and cooldown==0 and not eodClose:
            thrdRevPending=False; deepBlockDir=0; entryWasDeep=False
            slAmt = (slBelowSma if (smaVal is not None and c<smaVal) else slAboveSma) if enableSmaSL else slPts
            if thrdRevDir==1:
                tradeDir=1; entryPrice=c; entrySlope=legSlope; inTrade=True; activeSL=slAmt
                trailStop=None; bestPrice=None
                slExitDir=0; slEntryPrice=None; barrierBuf=None
            elif thrdRevDir==-1:
                tradeDir=-1; entryPrice=c; entrySlope=legSlope; inTrade=True; activeSL=slAmt
                trailStop=None; bestPrice=None
                slExitDir=0; slEntryPrice=None; barrierBuf=None

        # ===== deep block clear =====
        if enableDeepBlock and deepBlockDir!=0 and deepBestPrice is not None:
            if (deepBlockDir==1 and h>=deepBestPrice) or (deepBlockDir==-1 and l<=deepBestPrice):
                deepBlockDir=0; deepBestPrice=None
        inDeepBlock = enableDeepBlock and deepBlockDir!=0

        # ===== entry signals =====
        _calmOk = (calmSkipMult<=0.0) or (atrVal is not None and atrLong is not None and atrVal >= calmSkipMult*atrLong)
        canTrade = (not inTrade and cooldown==0 and not eodClose and not nyOpenBlock
                    and not lnOpenBlock and not preNYBlock and not ethOpenBlock and legSlope is not None and _calmOk)
        bigEnough = (not enableBodyFilter) or (abs(c-o) >= minBodyPts)
        isDeepSignal = legSlope is not None and abs(legSlope) >= deepSlope

        deepLossBlockLong=False; deepLossBlockShort=False
        if deepLossBlockDir!=0:
            if enableDeepLossOpp:
                deepLossBlockLong = deepLossBlockDir==1 or (deepLossBlockDir==-1 and not isDeepSignal)
                deepLossBlockShort= deepLossBlockDir==-1 or (deepLossBlockDir==1 and not isDeepSignal)
            else:
                deepLossBlockLong = deepLossBlockDir==1 and not isDeepSignal
                deepLossBlockShort= deepLossBlockDir==-1 and not isDeepSignal

        # ===== breach-fade OVERRIDE entry (before normal entries) =====
        breachActive = False
        if enableBreachFade:
            sessionOK = (not eodClose and not nyOpenBlock and not lnOpenBlock and not preNYBlock and not ethOpenBlock)
            shortDue = barsSinceSup is not None and barsSinceSup==breachFadeBars and sessionOK
            longDue  = barsSinceRes is not None and barsSinceRes==breachFadeBars and sessionOK
            _slAmt = (slBelowSma if (smaVal is not None and c<smaVal) else slAboveSma) if enableSmaSL else slPts
            if shortDue and breachTradeDir!=-1:
                if inTrade:  # reverse an open position first
                    close_trade(c,"BF-rev")
                tradeDir=-1; entryPrice=c; entrySlope=legSlope; inTrade=True; breachTradeDir=-1
                activeSL = _slAmt if breachFadeSL else 1e9   # 1e9 = effectively no SL
                trailStop=None; bestPrice=None; slExitDir=0; slEntryPrice=None; barrierBuf=None
                entryWasDeep=False; barsInTrade=0
            elif longDue and breachTradeDir!=1:
                if inTrade:
                    close_trade(c,"BF-rev")
                tradeDir=1; entryPrice=c; entrySlope=legSlope; inTrade=True; breachTradeDir=1
                activeSL = _slAmt if breachFadeSL else 1e9
                trailStop=None; bestPrice=None; slExitDir=0; slEntryPrice=None; barrierBuf=None
                entryWasDeep=False; barsInTrade=0
            breachActive = breachTradeDir!=0 or shortDue or longDue

        vwapBlock = (vwap_block is not None and bi < len(vwap_block) and vwap_block[bi])
        bigBlk = bigLossBlock>0
        if angleEntry:
            _trigLong  = legSlopeAngle is not None and legSlopeAngle <= -angleThresh
            _trigShort = legSlopeAngle is not None and legSlopeAngle >=  angleThresh
        else:
            _trigLong  = legSlope is not None and legSlope < -slopeEntry
            _trigShort = legSlope is not None and legSlope >  slopeEntry
        bullEntry = (canTrade and not breachActive and bigEnough and not inFractalDrought and _trigLong
                     and slExitDir!=1 and not srBlock and (not inDeepBlock or isDeepSignal)
                     and not deepLossBlockLong and not vwapBlock and not bigBlk)
        bearEntry = (canTrade and not breachActive and bigEnough and not inFractalDrought and _trigShort
                     and slExitDir!=-1 and not srBlock and (not inDeepBlock or isDeepSignal)
                     and not deepLossBlockShort and not vwapBlock and not bigBlk)

        # Delayed-entry interception: extreme slope while price is ABOVE the SMA -> don't
        # enter now; arm a delay and re-confirm the slope after delayBars bars.
        _delayOn = delayExtremeSlope>0 and delayBars>0 and smaVal is not None and c>smaVal \
                   and legSlope is not None and abs(legSlope)>=delayExtremeSlope
        if (bullEntry or bearEntry) and _delayOn and delayPending==0:
            delayPending = delayBars
            delayDir     = 1 if bullEntry else -1
            bullEntry=False; bearEntry=False   # suppress the immediate entry

        if bullEntry:
            slAmt = (slBelowSma if (smaVal is not None and c<smaVal) else slAboveSma) if enableSmaSL else slPts
            if extremeSlope>0 and extremeSL>0 and legSlope is not None and abs(legSlope)>=extremeSlope:
                slAmt = extremeSL
            tradeDir=1; entryPrice=c; entrySlope=legSlope; inTrade=True; activeSL=slAmt
            trailStop=None; bestPrice=None
            slExitDir=0; slEntryPrice=None; barrierBuf=None
            entryWasDeep=isDeepSignal; deepBlockDir=0; deepLossBlockDir=0
        elif bearEntry:
            slAmt = (slBelowSma if (smaVal is not None and c<smaVal) else slAboveSma) if enableSmaSL else slPts
            if extremeSlope>0 and extremeSL>0 and legSlope is not None and abs(legSlope)>=extremeSlope:
                slAmt = extremeSL
            tradeDir=-1; entryPrice=c; entrySlope=legSlope; inTrade=True; activeSL=slAmt
            trailStop=None; bestPrice=None
            slExitDir=0; slEntryPrice=None; barrierBuf=None
            entryWasDeep=isDeepSignal; deepBlockDir=0; deepLossBlockDir=0

        # ===== delayed extreme-above-SMA entry resolution =====
        # Count down; when it reaches 0 enter same dir IF slope still valid (same side,
        # beyond slopeEntry) and we can trade. If it fizzled, drop it (no trade).
        if delayPending>0 and inTrade:
            delayPending=0; delayDir=0   # a trade opened elsewhere -> drop the pending delay
        elif delayPending>0 and not (bullEntry or bearEntry):
            delayPending -= 1
            if delayPending==0:
                stillValid = (legSlope is not None and
                              ((delayDir==1 and legSlope < -slopeEntry) or
                               (delayDir==-1 and legSlope > slopeEntry)))
                if stillValid and canTrade and not inTrade and not vwapBlock and bigEnough \
                   and not inFractalDrought:
                    slAmt = (slBelowSma if (smaVal is not None and c<smaVal) else slAboveSma) if enableSmaSL else slPts
                    if extremeSlope>0 and extremeSL>0 and abs(legSlope)>=extremeSlope:
                        slAmt = extremeSL
                    tradeDir=delayDir; entryPrice=c; entrySlope=legSlope; inTrade=True; activeSL=slAmt
                    trailStop=None; bestPrice=None
                    slExitDir=0; slEntryPrice=None; barrierBuf=None
                    entryWasDeep=isDeepSignal; deepBlockDir=0; deepLossBlockDir=0
                delayDir=0

        # ===== trailing stop (skips breach-fade trades) =====
        if tradeDir==1 and inTrade and breachTradeDir==0:
            bestPrice = h if bestPrice is None else max(bestPrice,h)
            exitBestPrice=bestPrice
            if bestPrice-entryPrice >= trailTrigger:
                ad = trailDistStrong if (legSlope is not None and legSlope <= -deepSlope) else trailDist
                ts = bestPrice-ad
                trailStop = ts if trailStop is None else max(trailStop,ts)
            if trailStop is not None and l <= trailStop:
                close_trade(trailStop,"TRAIL")
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; cooldown=activeCooldown
        elif tradeDir==-1 and inTrade and breachTradeDir==0:
            bestPrice = l if bestPrice is None else min(bestPrice,l)
            exitBestPrice=bestPrice
            if entryPrice-bestPrice >= trailTrigger:
                ad = trailDistStrong if (legSlope is not None and legSlope <= -deepSlope) else trailDist
                ts = bestPrice+ad
                trailStop = ts if trailStop is None else min(trailStop,ts)
            if trailStop is not None and h >= trailStop:
                close_trade(trailStop,"TRAIL")
                tradeDir=0; trailStop=None; bestPrice=None; inTrade=False; cooldown=activeCooldown
        else:
            trailStop=None; bestPrice=None

        # ===== deep-loss record (posClosed bookkeeping) =====
        # In pine this is in the posClosed block using closedtrades.profit. We emulate:
        # whenever a trade just closed this bar with a loss and was deep, set deepLossBlockDir.
        # Detect: last trade appended this bar.
        # (handled by checking trades growth — simpler: set on each close above)

    return trades

def stats(trades):
    n=len(trades)
    if n==0: return dict(n=0,pnl=0,win=0,winrate=0)
    pnl=sum(t[3] for t in trades)
    wins=sum(1 for t in trades if t[3]>0)
    return dict(n=n, pnl=round(pnl,1), wins=wins, winrate=round(wins/n*100,1),
                avg=round(pnl/n,2))

if __name__=="__main__":
    bars=load()
    print(f"loaded {len(bars)} bars, {bars[0][0]} -> {bars[-1][0]}")
    base=dict(slopeEntry=1.7, slAboveSma=50.0, slBelowSma=30.0, tpPts=40.0, tpMult=3.0,
              trailTrigger=30.0, trailDist=10.0, trailDistStrong=10.0,
              tExpBars=30, tExpHardBars=20, tExpHardSlope=1.0)
    tr=run(bars,base)
    print("BASELINE:", stats(tr))
    from collections import Counter
    print("exit reasons:", Counter(t[4] for t in tr))
