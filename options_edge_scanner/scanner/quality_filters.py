"""Conservative offline quality filters for research-only scanner inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class OfflineScanQualitySettings:
    """Small, conservative quality controls for offline research/demo scans."""

    max_abs_moneyness_pct: float | None = 0.25
    max_debit_fraction_of_width: float | None = 0.67
    max_bid_ask_spread_pct: float | None = 0.25
    max_spread_market_width_pct: float | None = 0.8
    min_volume: float | None = None
    min_open_interest: float | None = None
    min_abs_delta: float | None = None
    max_abs_delta: float | None = None
    min_liquidity_score: float | None = None
    execution_slippage_floor: float = 0.2
    execution_slippage_cap: float = 0.5
    min_expected_value: float = 0.0
    min_probability_of_profit: float = 0.3
    top_n: int = 20
    max_positions_per_ticker: int | None = None
    max_positions_per_expiration: int | None = None


def _find_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    normalized_map = {str(column).lower(): column for column in columns}
    for candidate in candidates:
        matched = normalized_map.get(candidate.lower())
        if matched is not None:
            return matched
    return None


def _finite_numeric(series: pd.Series) -> pd.Series:
    """Parse one numeric series and keep only finite values."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(
        numeric.notna() & numeric.map(lambda value: math.isfinite(float(value)) if pd.notna(value) else False)
    )


def apply_option_quote_quality_filters(
    option_quotes: pd.DataFrame,
    *,
    settings: OfflineScanQualitySettings,
) -> pd.DataFrame:
    """Filter obviously poor-quality local quote rows before spread generation."""
    if option_quotes.empty:
        return option_quotes.copy()

    working = option_quotes.copy()
    keep_mask = pd.Series(True, index=working.index)

    strike_col = _find_column(working.columns, ["strike", "strike_price", "strikeprice"])
    underlying_col = _find_column(
        working.columns,
        ["underlying_price", "spot_price", "spot", "stock_price", "underlying"],
    )

    if (
        settings.max_abs_moneyness_pct is not None
        and strike_col is not None
        and underlying_col is not None
    ):
        strikes = _finite_numeric(working[strike_col])
        spots = _finite_numeric(working[underlying_col])
        moneyness_distance = (strikes - spots).abs() / spots
        keep_mask &= (spots > 0) & moneyness_distance.le(settings.max_abs_moneyness_pct)
    elif strike_col is not None:
        strikes = _finite_numeric(working[strike_col])
        keep_mask &= strikes.gt(0)
    elif underlying_col is not None:
        spots = _finite_numeric(working[underlying_col])
        keep_mask &= spots.gt(0)

    bid_col = _find_column(working.columns, ["bid"])
    ask_col = _find_column(working.columns, ["ask"])
    mid_col = _find_column(working.columns, ["mid", "mark", "price", "last", "last_price", "close"])
    if (
        settings.max_bid_ask_spread_pct is not None
        and bid_col is not None
        and ask_col is not None
    ):
        bids = _finite_numeric(working[bid_col])
        asks = _finite_numeric(working[ask_col])
        mids = (
            _finite_numeric(working[mid_col])
            if mid_col is not None
            else (bids + asks) / 2.0
        )
        relative_spread = (asks - bids) / mids
        keep_mask &= (
            bids.ge(0)
            & asks.ge(0)
            & asks.ge(bids)
            & mids.gt(0)
            & relative_spread.le(settings.max_bid_ask_spread_pct)
        )
    else:
        if bid_col is not None:
            bids = _finite_numeric(working[bid_col])
            keep_mask &= bids.ge(0)
        if ask_col is not None:
            asks = _finite_numeric(working[ask_col])
            keep_mask &= asks.ge(0)

    volume_col = _find_column(working.columns, ["volume"])
    if settings.min_volume is not None and volume_col is not None:
        volumes = pd.to_numeric(working[volume_col], errors="coerce")
        keep_mask &= volumes.ge(settings.min_volume)

    open_interest_col = _find_column(working.columns, ["open_interest", "openinterest", "oi"])
    if settings.min_open_interest is not None and open_interest_col is not None:
        open_interest = pd.to_numeric(working[open_interest_col], errors="coerce")
        keep_mask &= open_interest.ge(settings.min_open_interest)

    delta_col = _find_column(working.columns, ["delta"])
    if delta_col is not None and (
        settings.min_abs_delta is not None or settings.max_abs_delta is not None
    ):
        abs_delta = pd.to_numeric(working[delta_col], errors="coerce").abs()
        if settings.min_abs_delta is not None:
            keep_mask &= abs_delta.ge(settings.min_abs_delta)
        if settings.max_abs_delta is not None:
            keep_mask &= abs_delta.le(settings.max_abs_delta)

    implied_vol_col = _find_column(working.columns, ["implied_vol", "implied_volatility", "iv"])
    if implied_vol_col is not None:
        implied_vol = _finite_numeric(working[implied_vol_col])
        keep_mask &= implied_vol.gt(0)

    return working.loc[keep_mask].reset_index(drop=True)


def apply_spread_quality_filters(
    spreads: pd.DataFrame,
    *,
    settings: OfflineScanQualitySettings,
) -> pd.DataFrame:
    """Filter spread rows that are structurally poor demo/research candidates."""
    if spreads.empty:
        return spreads.copy()

    working = spreads.copy()
    keep_mask = pd.Series(True, index=working.index)

    debit = _finite_numeric(working.get("debit"))
    width = _finite_numeric(working.get("width"))
    max_profit = _finite_numeric(working.get("max_profit"))
    keep_mask &= debit.gt(0) & width.gt(0) & debit.lt(width) & max_profit.gt(0)

    if settings.max_debit_fraction_of_width is not None:
        debit_fraction = debit / width
        keep_mask &= debit_fraction.le(settings.max_debit_fraction_of_width)

    if (
        settings.max_spread_market_width_pct is not None
        and "spread_market_width" in working.columns
    ):
        quoted_debit = pd.to_numeric(
            working.get("quoted_debit", working.get("debit")),
            errors="coerce",
        )
        quoted_debit = _finite_numeric(quoted_debit)
        spread_market_width = _finite_numeric(working["spread_market_width"])
        relative_market_width = spread_market_width / quoted_debit
        keep_mask &= quoted_debit.gt(0) & spread_market_width.ge(0)
        keep_mask &= relative_market_width.le(settings.max_spread_market_width_pct)

    if settings.min_liquidity_score is not None and "liquidity_score" in working.columns:
        liquidity_score = pd.to_numeric(working["liquidity_score"], errors="coerce")
        keep_mask &= liquidity_score.ge(settings.min_liquidity_score)

    if "underlying_price" in working.columns:
        underlying_price = _finite_numeric(working["underlying_price"])
        keep_mask &= underlying_price.gt(0)
    if "implied_volatility" in working.columns:
        implied_volatility = _finite_numeric(working["implied_volatility"])
        keep_mask &= implied_volatility.gt(0)

    return working.loc[keep_mask].reset_index(drop=True)
