"""
Formats the daily briefing as plain text and as a JSON record.
ATR-based entry/stop/target levels are computed here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os

BRIEFINGS_DIR = os.path.join(os.path.dirname(__file__), "briefings")
MAX_BRIEFINGS = 5

# Risk/reward ratio used for target calculation
RR_RATIO = 2.0

# ATR multipliers
STOP_ATR_MULT = 1.0   # stop = entry ± 1 ATR
TARGET_ATR_MULT = RR_RATIO  # target = entry ± 2 ATR


def _atr_levels(close: float, atr: float, direction: str) -> dict:
    """Compute entry, stop, and target from ATR."""
    if atr == 0:
        return {"entry": close, "stop": None, "target": None}

    if direction == "up":
        entry = round(close, 4)
        stop = round(close - STOP_ATR_MULT * atr, 4)
        target = round(close + TARGET_ATR_MULT * atr, 4)
    else:
        entry = round(close, 4)
        stop = round(close + STOP_ATR_MULT * atr, 4)
        target = round(close - TARGET_ATR_MULT * atr, 4)

    return {"entry": entry, "stop": stop, "target": target}


def _eu_atr_levels(eu_data: dict, corr: dict) -> dict:
    """Compute ATR-based levels for an EU stock using its own ATR."""
    close = eu_data.get("close", 0)
    atr = eu_data.get("atr", 0)
    direction = corr["direction"]
    return _atr_levels(close, atr, direction)


def format_text_briefing(
    run_ts: str,
    asian_movers: list[dict],
    correlated_eu: list[dict],
    eu_data: dict[str, dict],  # {ticker: {close, atr, pct_change, ...}}
) -> str:
    """Render the briefing as a human-readable plain-text string."""
    lines = []
    sep = "=" * 72

    lines.append(sep)
    lines.append(f"  ASIA-EU MARKET BRIEFING  |  Generated {run_ts} UTC")
    lines.append(sep)

    # --- Asian movers ---
    lines.append("")
    if not asian_movers:
        lines.append("ASIAN MOVERS:  None met the 2.5% move + 1.5x volume threshold.")
    else:
        lines.append(f"ASIAN MOVERS  (≥2.5% move, ≥1.5× avg volume)")
        lines.append("-" * 72)
        for m in asian_movers:
            arrow = "▲" if m["direction"] == "up" else "▼"
            lines.append(
                f"  {arrow} {m['name']:20s} ({m['symbol']:8s})  "
                f"{m['pct_change']:+.2f}%  "
                f"Vol×{m['volume_ratio']:.2f}  "
                f"Close {m['close']:,.2f}  ATR {m['atr']:,.2f}"
            )

    # --- EU watchlist at open ---
    lines.append("")
    if not correlated_eu:
        lines.append("EU STOCKS TO WATCH:  None flagged (no Asian movers).")
    else:
        lines.append(f"EU STOCKS TO WATCH AT OPEN  (ranked by estimated impact)")
        lines.append("-" * 72)
        for c in correlated_eu:
            ticker = c["eu_ticker"]
            ed = eu_data.get(ticker, {})
            close = ed.get("close", 0)
            atr = ed.get("atr", 0)
            prev_pct = ed.get("pct_change", 0)
            lvls = _eu_atr_levels(ed, c)

            arrow = "▲" if c["direction"] == "up" else "▼"
            est = c["estimated_eu_move_pct"]

            lines.append("")
            lines.append(
                f"  {arrow} {c['eu_name']:22s} ({ticker})   est. {est:+.2f}%"
            )
            lines.append(f"     Driven by: {c['asian_name']} ({c['asian_pct']:+.2f}%)  β={c['beta']:.2f}")
            lines.append(f"     Reason:    {c['reason']}")
            if close and atr:
                lines.append(
                    f"     Last close {close:,.4f}  |  ATR {atr:,.4f}  |  Prev session {prev_pct:+.2f}%"
                )
                lines.append(
                    f"     Entry ~{lvls['entry']:,.4f}  |  Stop {lvls['stop']:,.4f}  |  Target {lvls['target']:,.4f}  (1:{RR_RATIO:.0f} RR)"
                )

    lines.append("")
    lines.append(sep)
    lines.append("Disclaimer: Indicative only. Not financial advice.")
    lines.append(sep)
    lines.append("")
    return "\n".join(lines)


def build_json_record(
    run_ts: str,
    asian_movers: list[dict],
    correlated_eu: list[dict],
    eu_data: dict[str, dict],
) -> dict:
    """Build the structured JSON record for a single briefing run."""
    eu_entries = []
    for c in correlated_eu:
        ticker = c["eu_ticker"]
        ed = eu_data.get(ticker, {})
        lvls = _eu_atr_levels(ed, c)
        eu_entries.append({
            **c,
            "close": ed.get("close"),
            "atr": ed.get("atr"),
            "prev_pct_change": ed.get("pct_change"),
            "entry": lvls["entry"],
            "stop": lvls["stop"],
            "target": lvls["target"],
            "rr_ratio": RR_RATIO,
        })

    return {
        "generated_at": run_ts,
        "asian_movers": asian_movers,
        "eu_watchlist": eu_entries,
    }


def save_briefing(record: dict) -> str:
    """Persist a briefing JSON record; keep only the last MAX_BRIEFINGS files."""
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    ts_safe = record["generated_at"].replace(":", "-").replace(" ", "_")
    filename = f"briefing_{ts_safe}.json"
    path = os.path.join(BRIEFINGS_DIR, filename)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=2)

    # Prune old briefings
    all_files = sorted(
        [f for f in os.listdir(BRIEFINGS_DIR) if f.endswith(".json")],
        reverse=True,
    )
    for old in all_files[MAX_BRIEFINGS:]:
        os.remove(os.path.join(BRIEFINGS_DIR, old))

    return path


def load_last_briefings(n: int = MAX_BRIEFINGS) -> list[dict]:
    """Load the n most recent briefing JSON records."""
    if not os.path.isdir(BRIEFINGS_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(BRIEFINGS_DIR) if f.endswith(".json")],
        reverse=True,
    )[:n]
    records = []
    for fname in files:
        with open(os.path.join(BRIEFINGS_DIR, fname)) as fh:
            records.append(json.load(fh))
    return records
