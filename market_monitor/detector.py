"""
Flags movers: >2.5% price move AND volume spike >1.5x 20-day average.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from fetcher import get_latest_session

MOVE_THRESHOLD_PCT = 2.5
VOLUME_SPIKE_RATIO = 1.5
ATR_PERIOD = 14


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    """Average True Range over the last `period` sessions."""
    if df is None or len(df) < period + 1:
        return 0.0

    high = df["High"]
    low = df["Low"]
    close = df["Close"].shift(1)

    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low - close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]
    return round(float(atr), 6)


def is_mover(session: dict) -> bool:
    """Return True if the session meets both move and volume thresholds."""
    return (
        abs(session.get("pct_change", 0)) >= MOVE_THRESHOLD_PCT
        and session.get("volume_ratio", 0) >= VOLUME_SPIKE_RATIO
    )


def build_mover_report(symbol: str, name: str, session: dict, atr: float) -> dict:
    """Assemble a structured mover record."""
    direction = "up" if session["pct_change"] > 0 else "down"
    return {
        "symbol": symbol,
        "name": name,
        "date": session["date"],
        "direction": direction,
        "pct_change": session["pct_change"],
        "close": session["close"],
        "prev_close": session["prev_close"],
        "volume": session["volume"],
        "avg_volume_20d": session["avg_volume_20d"],
        "volume_ratio": session["volume_ratio"],
        "atr": atr,
        "high": session["high"],
        "low": session["low"],
    }


def detect_movers(
    data: dict[str, pd.DataFrame],
    names: dict[str, str],
) -> list[dict]:
    """
    Given a dict of {symbol: DataFrame}, return a list of mover records
    for anything that tripped both thresholds.
    """
    movers = []
    for symbol, df in data.items():
        session = get_latest_session(df)
        if not session:
            continue
        if is_mover(session):
            atr = compute_atr(df)
            name = names.get(symbol, symbol)
            movers.append(build_mover_report(symbol, name, session, atr))

    # Sort by absolute % move descending
    movers.sort(key=lambda r: abs(r["pct_change"]), reverse=True)
    return movers
