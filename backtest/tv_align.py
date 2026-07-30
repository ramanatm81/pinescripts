#!/usr/bin/env python3
"""
Align my sim's trades against the TradingView Strategy Tester export, matched by ENTRY timestamp,
to pinpoint exactly which entries/exits diverge. TV file = the Slope-Touch_Fade_Strategy export.

Prints, per TV trade: entry time, TV entry/exit/reason, and whether my sim has a matching entry
at that bar, with my exit. Flags MISSING entries (TV has, I don't) and EXTRA entries (I have, TV
doesn't) -- that's what breaks the trade-by-trade alignment.
"""
import csv
from datetime import datetime, timezone, timedelta
import slope_touch_fade_bt as bt

TV_CSV = "/Users/maheshk81/Downloads/Slope-Touch_Fade_Strategy_CME_MINI_MNQ1!_2026-07-29.csv"
LDN = timezone(timedelta(hours=1))   # the OOS file / TV export are London +01:00


def tv_trades():
    rows = list(csv.DictReader(open(TV_CSV, encoding="utf-8-sig")))
    en = {r["Trade number"]: r for r in rows if "Entry" in r["Type"]}
    ex = {r["Trade number"]: r for r in rows if "Exit" in r["Type"]}
    out = []
    for tn in sorted(en, key=int):
        e, x = en[tn], ex[tn]
        d = 1 if "long" in e["Type"] else -1
        out.append(dict(n=int(tn), dir=d,
                        etime=e["Date and time"], eprice=float(e["Price USD"]),
                        xtime=x["Date and time"], xprice=float(x["Price USD"]),
                        reason=x["Signal"], usd=float(x["Net PnL USD"])))
    return out


def my_trades_with_time():
    """Re-run the sim but capture the entry bar's London time for each trade."""
    boos = bt.load(bt.OOS)
    sig = bt.detect(boos)
    long_sig, short_sig, _fl, _fs = sig
    ctmin = [b[0] for b in boos]; close = [b[4] for b in boos]; epoch = [b[5] for b in boos]
    n = len(boos)
    pos = 0; entry_px = None; entry_i = None
    out = []

    def ldn(i):
        return datetime.fromtimestamp(epoch[i], tz=LDN).strftime("%Y-%m-%d %H:%M")

    for i in range(n):
        cm = ctmin[i]
        gap = i > 0 and (epoch[i] - epoch[i - 1]) / 60.0 > 60
        sflat = (900 <= cm < 960) or (510 <= cm < 540) or (120 <= cm < 150) or gap
        if pos > 0 and short_sig[i]:
            out.append((ldn(entry_i), pos, entry_px, ldn(i), close[i], "opposite")); pos = 0
        elif pos < 0 and long_sig[i]:
            out.append((ldn(entry_i), pos, entry_px, ldn(i), close[i], "opposite")); pos = 0
        if sflat and pos != 0:
            out.append((ldn(entry_i), pos, entry_px, ldn(i), close[i], "session")); pos = 0
        if pos == 0 and not sflat:
            if long_sig[i] and not short_sig[i]:
                pos = 1; entry_px = close[i]; entry_i = i
            elif short_sig[i] and not long_sig[i]:
                pos = -1; entry_px = close[i]; entry_i = i
    if pos != 0:
        out.append((ldn(entry_i), pos, entry_px, ldn(n - 1), close[-1], "open"))
    return out


def main():
    tv = tv_trades()
    mine = my_trades_with_time()
    mine_by_etime = {m[0]: m for m in mine}
    print(f"TV trades: {len(tv)}   MY trades: {len(mine)}\n")
    print("TV# dir  entry_time         TVentry  TVexit  reason   | MY match? myexit  myreason")
    for t in tv:
        m = mine_by_etime.get(t["etime"])
        if m:
            tag = "OK " if abs(m[2] - t["eprice"]) < 0.5 else "PX!"
            print(f"{t['n']:>3} {t['dir']:+d}  {t['etime']}  {t['eprice']:>8} {t['xprice']:>8} {t['reason']:<8} | {tag} {m[4]:>8} {m[5]}")
        else:
            print(f"{t['n']:>3} {t['dir']:+d}  {t['etime']}  {t['eprice']:>8} {t['xprice']:>8} {t['reason']:<8} | MISSING (my sim took no entry here)")
    # extra entries mine has that TV doesn't
    tv_etimes = {t["etime"] for t in tv}
    extra = [m for m in mine if m[0] not in tv_etimes]
    if extra:
        print("\nEXTRA entries my sim took that TV did NOT:")
        for m in extra:
            print(f"   {m[0]}  dir={m[1]:+d} entry={m[2]}")


if __name__ == "__main__":
    main()
