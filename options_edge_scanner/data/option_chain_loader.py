"""Legacy live option-chain loader kept for narrow compatibility only."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
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
    "quote_observed_at",
    "underlying_price_observed_at",
    "underlying_price_source",
]


def _normalize_side(
    frame: pd.DataFrame,
    *,
    ticker: str,
    expiration: str,
    option_type: str,
    underlying_price: float,
    quote_observed_at: str,
    underlying_price_observed_at: str,
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
            "quote_observed_at": quote_observed_at,
            "underlying_price_observed_at": underlying_price_observed_at,
            "underlying_price_source": "history.close",
        }
    )

    for col in ("strike", "bid", "ask", "implied_vol", "underlying_price"):
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized["mid"] = (normalized["bid"] + normalized["ask"]) / 2.0
    normalized["expiration"] = pd.to_datetime(normalized["expiration"], errors="coerce")
    normalized["quote_observed_at"] = pd.to_datetime(normalized["quote_observed_at"], errors="coerce")
    normalized["underlying_price_observed_at"] = pd.to_datetime(
        normalized["underlying_price_observed_at"],
        errors="coerce",
    )

    return normalized[OUTPUT_COLUMNS]


def _safe_underlying_price(ticker_obj: Any) -> tuple[float, str]:
    """Get the latest underlying price plus its observed timestamp."""
    history = ticker_obj.history(period="1d")
    if history.empty:
        return float("nan"), ""

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        return float("nan"), ""

    observed_at = pd.to_datetime(history.index[-1], errors="coerce", utc=True)
    observed_at_str = ""
    if not pd.isna(observed_at):
        observed_at_str = observed_at.tz_convert(None).isoformat() + "Z"
    return float(close.iloc[-1]), observed_at_str


def load_option_chain(ticker: str) -> pd.DataFrame:
    """Load calls and puts for all expirations into a research-only dataframe."""
    yf = importlib.import_module("yfinance")
    ticker_obj = yf.Ticker(ticker)
    expirations = list(ticker_obj.options or [])

    if not expirations:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    quote_observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    underlying_price, underlying_price_observed_at = _safe_underlying_price(ticker_obj)
    all_frames: List[pd.DataFrame] = []

    for expiration in expirations:
        chain = ticker_obj.option_chain(expiration)
        calls = _normalize_side(
            chain.calls,
            ticker=ticker,
            expiration=expiration,
            option_type="call",
            underlying_price=underlying_price,
            quote_observed_at=quote_observed_at,
            underlying_price_observed_at=underlying_price_observed_at,
        )
        puts = _normalize_side(
            chain.puts,
            ticker=ticker,
            expiration=expiration,
            option_type="put",
            underlying_price=underlying_price,
            quote_observed_at=quote_observed_at,
            underlying_price_observed_at=underlying_price_observed_at,
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
