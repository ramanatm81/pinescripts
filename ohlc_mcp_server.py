#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp[cli]>=1.0.0",
#   "python-dateutil>=2.8.2",
# ]
# ///
"""
MCP stdio server — exposes OHLC bar data from ~/Downloads/data.csv to Claude.

Run via uv (auto-installs deps):
  uv run /Users/maheshk81/ohlc_mcp_server.py

Configured automatically via .claude/settings.json
"""

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as dtparser
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

CSV_PATH = Path.home() / "Downloads" / "data.csv"

# All columns we want to return (in order). If a column is missing from the CSV it is skipped.
ALL_COLUMNS = [
    "time", "open", "high", "low", "close",
    "legSlope", "tradeLegSlope", "activeSL", "SMA",
    "inTrade", "tradeDir", "barsInTrade", "cooldown", "isDoji", "Volume",
]

server = Server("ohlc-data-server")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(s: str, tz_name: str) -> datetime:
    """Parse a datetime string; localise to tz_name if naive."""
    dt = dtparser.parse(s)
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo          # Python 3.9+
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except ImportError:
            import pytz
            dt = pytz.timezone(tz_name).localize(dt)
    return dt


def _coerce(key: str, val: str):
    """Return val coerced to the right type; empty string becomes None."""
    if val == "" or val is None:
        return None
    int_cols = {"inTrade", "tradeDir", "barsInTrade", "cooldown", "isDoji", "Volume"}
    if key in int_cols:
        try:
            return int(float(val))
        except ValueError:
            return None
    try:
        return float(val)
    except ValueError:
        return val  # keep as string (e.g. "time")


def _load_range(start: datetime, end: datetime) -> list[dict]:
    """Read CSV and return all-column bars whose timestamp falls in [start, end]."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    start_utc = start.astimezone(timezone.utc)
    end_utc   = end.astimezone(timezone.utc)
    bars      = []

    with open(CSV_PATH, newline="") as fh:
        reader = csv.DictReader(fh)
        csv_cols = reader.fieldnames or []
        for row in reader:
            try:
                bar_dt = dtparser.parse(row["time"])
                if bar_dt.tzinfo is None:
                    bar_dt = bar_dt.replace(tzinfo=timezone.utc)
                bar_utc = bar_dt.astimezone(timezone.utc)
                if start_utc <= bar_utc <= end_utc:
                    bar = {}
                    for col in ALL_COLUMNS:
                        if col in csv_cols:
                            bar[col] = _coerce(col, row.get(col, ""))
                    bars.append(bar)
            except (ValueError, KeyError):
                continue

    return bars


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_ohlc_data",
            description=(
                "Fetch all strategy columns from the trading data CSV (~/Downloads/data.csv) "
                "for a given time range. Returns every available column: "
                "time, open, high, low, close, legSlope, tradeLegSlope, activeSL, SMA, "
                "inTrade, tradeDir, barsInTrade, cooldown, isDoji, Volume. "
                "Missing/empty values are returned as null. "
                "Also returns a summary: bar count, range high/low, price range."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": (
                            "Start of range. ISO 8601 preferred, e.g. '2026-05-04T02:00:00' "
                            "or '2026-05-04 02:00'. Naive times use the timezone parameter."
                        ),
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End of range (inclusive). Same format as start_time.",
                    },
                    "timezone": {
                        "type": "string",
                        "description": (
                            "IANA timezone for interpreting naive datetimes. "
                            "Default: 'America/Chicago'."
                        ),
                        "default": "America/Chicago",
                    },
                },
                "required": ["start_time", "end_time"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "get_ohlc_data":
        raise ValueError(f"Unknown tool: {name}")

    tz_name = arguments.get("timezone", "America/Chicago")

    # --- parse datetimes ---
    try:
        start_dt = _parse_dt(arguments["start_time"], tz_name)
        end_dt   = _parse_dt(arguments["end_time"],   tz_name)
    except Exception as exc:
        out = {"error": f"Could not parse datetime inputs: {exc}", "bars": [], "summary": None}
        return [TextContent(type="text", text=json.dumps(out, indent=2))]

    if start_dt > end_dt:
        out = {"error": "start_time must be before end_time", "bars": [], "summary": None}
        return [TextContent(type="text", text=json.dumps(out, indent=2))]

    # --- read CSV ---
    try:
        bars = _load_range(start_dt, end_dt)
    except FileNotFoundError as exc:
        out = {"error": str(exc), "bars": [], "summary": None}
        return [TextContent(type="text", text=json.dumps(out, indent=2))]
    except Exception as exc:
        out = {"error": f"Error reading CSV: {exc}", "bars": [], "summary": None}
        return [TextContent(type="text", text=json.dumps(out, indent=2))]

    # --- build response ---
    if not bars:
        out = {
            "bars": [],
            "summary": {
                "bar_count": 0,
                "message": f"No bars found between {arguments['start_time']} and {arguments['end_time']}",
            },
        }
    else:
        highs = [b["high"] for b in bars if b.get("high") is not None]
        lows  = [b["low"]  for b in bars if b.get("low")  is not None]
        out   = {
            "bars": bars,
            "summary": {
                "bar_count":   len(bars),
                "first_bar":   bars[0]["time"],
                "last_bar":    bars[-1]["time"],
                "range_high":  max(highs) if highs else None,
                "range_low":   min(lows)  if lows  else None,
                "price_range": round(max(highs) - min(lows), 4) if highs and lows else None,
            },
        }

    return [TextContent(type="text", text=json.dumps(out, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
