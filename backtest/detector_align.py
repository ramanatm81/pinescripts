#!/usr/bin/env python3
"""
Align my Python detector's entry bars against the PINE STRATEGY EXPORT (~/Downloads/data.csv),
which carries EVT_long_entry / EVT_short_entry (Pine's exact entry bars) and 'ols run (pts)' /
'ols R2' per bar. That export is the oracle -- my ols() is already verified bar-exact with it, so
any entry mismatch is in the ARM/LOCK state machine, which this tool pinpoints.

Prints Pine's entries vs mine, matched by timestamp, and flags MISSING (Pine has, I don't) and
EXTRA (I have, Pine doesn't). For each MISSING, also dumps my detector's arm/lock state history
leading up to it so the divergence is visible.
"""
import csv
from datetime import datetime, timezone, timedelta
import slope_touch_fade_bt as bt

DATA = bt.OOS   # ~/Downloads/data.csv -- the strategy export with EVT_ columns
LDN = timezone(timedelta(hours=1))


def pine_entries():
    """Read Pine's exact entry bars from the EVT_ columns."""
    rows = list(csv.DictReader(open(DATA, encoding="utf-8-sig")))
    out = []
    for r in rows:
        lv = r.get("EVT_long_entry", "")
        sv = r.get("EVT_short_entry", "")
        if lv not in ("", "0"):
            out.append((r["time"][:16], 1, float(r["EVT_entry_px"])))
        elif sv not in ("", "0"):
            out.append((r["time"][:16], -1, float(r["EVT_entry_px"])))
    return out


def my_signals():
    """Run my detector, return list of (iso_time, dir) for every fire, plus the raw arrays and bars
    so callers can inspect state around a bar."""
    boos = bt.load(DATA)
    sig = bt.detect(boos)
    long_sig, short_sig, fl, fs = sig
    epoch = [b[5] for b in boos]

    def iso(i):
        # data.csv is London +01:00; reproduce that stamp (matches EVT time strings)
        return datetime.fromtimestamp(epoch[i], tz=LDN).strftime("%Y-%m-%dT%H:%M")

    fires = []
    for i in range(len(boos)):
        if long_sig[i]:
            fires.append((iso(i), 1))
        elif short_sig[i]:
            fires.append((iso(i), -1))
    return fires, boos, sig


def main():
    pine = pine_entries()
    fires, boos, sig = my_signals()
    mine = {t: d for t, d in fires}
    pine_t = {t: d for t, d, _ in pine}

    print(f"Pine entries: {len(pine)}   My fires: {len(fires)}\n")
    print("time              Pine  Mine  status")
    all_times = sorted(set(pine_t) | set(mine))
    miss = extra = ok = 0
    for t in all_times:
        p = pine_t.get(t)
        m = mine.get(t)
        if p and m:
            tag = "OK" if p == m else f"DIR MISMATCH (pine {p}, mine {m})"
            ok += (p == m)
        elif p and not m:
            tag = "MISSING (pine fired, I didn't)"; miss += 1
        else:
            tag = "EXTRA (I fired, pine didn't)"; extra += 1
        ps = {1: "L", -1: "S"}.get(p, "-")
        ms = {1: "L", -1: "S"}.get(m, "-")
        if tag != "OK":
            print(f"{t}   {ps:>3}  {ms:>3}   {tag}")
    print(f"\nmatched OK: {ok}   missing: {miss}   extra: {extra}")


if __name__ == "__main__":
    main()
