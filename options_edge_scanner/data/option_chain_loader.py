"""Utilities for loading and normalizing option-chain data."""

from __future__ import annotations

import importlib
from typing import Any, List

import pandas as pd


OUTPUT_COLUMNS = [
    "ticker",
    "expiration",
    "strike",
    "type",
    "bid",
    "ask",
    "mid",
    "implied_vol",
    "underlying_price",
]


def _normalize_side(
    frame: pd.DataFrame,
    *,
    ticker: str,
    expiration: str,
    option_type: str,
    underlying_price: float,
) -> pd.DataFrame:
    """Normalize one side of an option chain (calls or puts)."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    normalized = pd.DataFrame(
        {
            "ticker": ticker.upper(),
            "expiration": expiration,
            "strike": frame.get("strike"),
            "type": option_type,
            "bid": frame.get("bid"),
            "ask": frame.get("ask"),
            "implied_vol": frame.get("impliedVolatility"),
            "underlying_price": underlying_price,
        }
    )

    for col in ("strike", "bid", "ask", "implied_vol", "underlying_price"):
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized["bid"] = normalized["bid"].fillna(0.0)
    normalized["ask"] = normalized["ask"].fillna(0.0)
    normalized["mid"] = (normalized["bid"] + normalized["ask"]) / 2.0
    normalized["expiration"] = pd.to_datetime(normalized["expiration"], errors="coerce")

    return normalized[OUTPUT_COLUMNS]


def _safe_underlying_price(ticker_obj: Any) -> float:
    """Get the latest underlying price if available."""
    history = ticker_obj.history(period="1d")
    if history.empty:
        return float("nan")

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        return float("nan")

    return float(close.iloc[-1])


def load_option_chain(ticker: str) -> pd.DataFrame:
    """Load calls and puts for all expirations into a clean dataframe."""
    yf = importlib.import_module("yfinance")
    ticker_obj = yf.Ticker(ticker)
    expirations = list(ticker_obj.options or [])

    if not expirations:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    underlying_price = _safe_underlying_price(ticker_obj)
    all_frames: List[pd.DataFrame] = []

    for expiration in expirations:
        chain = ticker_obj.option_chain(expiration)
        calls = _normalize_side(
            chain.calls,
            ticker=ticker,
            expiration=expiration,
            option_type="call",
            underlying_price=underlying_price,
        )
        puts = _normalize_side(
            chain.puts,
            ticker=ticker,
            expiration=expiration,
            option_type="put",
            underlying_price=underlying_price,
        )
        all_frames.extend([calls, puts])

    combined = pd.concat(all_frames, ignore_index=True)
    combined = combined.dropna(subset=["expiration", "strike"])

    # Ensure stable dtypes in output
    combined["ticker"] = combined["ticker"].astype("string")
    combined["type"] = combined["type"].astype("string")
    combined["expiration"] = pd.to_datetime(combined["expiration"], errors="coerce")

    for col in ("strike", "bid", "ask", "mid", "implied_vol", "underlying_price"):
        combined[col] = pd.to_numeric(combined[col], errors="coerce")

    return combined[OUTPUT_COLUMNS].reset_index(drop=True)
