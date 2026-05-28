"""
Fetches overnight price/volume data for Asian indices and watchlist stocks.
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

ASIAN_INDICES = {
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng",
    "^AXJO": "ASX 200",
}


def fetch_ticker_data(symbol: str, lookback_days: int = 30) -> pd.DataFrame:
    """Download OHLCV data for a single ticker."""
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=lookback_days)
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            logger.warning("No data returned for %s", symbol)
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", symbol, exc)
        return None


def fetch_all_asian_indices(lookback_days: int = 30) -> dict[str, pd.DataFrame]:
    """Return a dict of DataFrames keyed by symbol for all Asian indices."""
    results = {}
    for symbol, name in ASIAN_INDICES.items():
        logger.info("Fetching %s (%s)", name, symbol)
        df = fetch_ticker_data(symbol, lookback_days)
        if df is not None:
            results[symbol] = df
    return results


def fetch_watchlist(symbols: list[str], lookback_days: int = 30) -> dict[str, pd.DataFrame]:
    """Return a dict of DataFrames for a list of ticker symbols."""
    results = {}
    for symbol in symbols:
        df = fetch_ticker_data(symbol, lookback_days)
        if df is not None:
            results[symbol] = df
    return results


def get_latest_session(df: pd.DataFrame) -> dict:
    """Extract key metrics for the most recent trading session."""
    if df is None or len(df) < 2:
        return {}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    open_price = float(latest["Open"].iloc[0] if hasattr(latest["Open"], "iloc") else latest["Open"])
    close_price = float(latest["Close"].iloc[0] if hasattr(latest["Close"], "iloc") else latest["Close"])
    prev_close = float(prev["Close"].iloc[0] if hasattr(prev["Close"], "iloc") else prev["Close"])
    high = float(latest["High"].iloc[0] if hasattr(latest["High"], "iloc") else latest["High"])
    low = float(latest["Low"].iloc[0] if hasattr(latest["Low"], "iloc") else latest["Low"])
    volume = float(latest["Volume"].iloc[0] if hasattr(latest["Volume"], "iloc") else latest["Volume"]) if "Volume" in latest else 0.0

    pct_change = (close_price - prev_close) / prev_close * 100 if prev_close else 0.0
    session_range = high - low

    avg_volume_20d = float(df["Volume"].iloc[-21:-1].mean()) if len(df) >= 21 else volume

    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "open": round(open_price, 4),
        "high": round(high, 4),
        "low": round(low, 4),
        "close": round(close_price, 4),
        "prev_close": round(prev_close, 4),
        "pct_change": round(pct_change, 4),
        "volume": int(volume),
        "avg_volume_20d": int(avg_volume_20d),
        "volume_ratio": round(volume / avg_volume_20d, 4) if avg_volume_20d else 1.0,
        "session_range": round(session_range, 4),
    }
