"""Conservative offline quality filters for research-only scanner inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class OfflineScanQualitySettings:
    """Small, conservative quality controls for offline research/demo scans."""

    max_abs_moneyness_pct: float | None = 0.25
    max_debit_fraction_of_width: float | None = 0.67
    max_bid_ask_spread_pct: float | None = 0.25
    min_volume: float | None = None
    min_open_interest: float | None = None
    min_abs_delta: float | None = None
    max_abs_delta: float | None = None


def _find_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    normalized_map = {str(column).lower(): column for column in columns}
    for candidate in candidates:
        matched = normalized_map.get(candidate.lower())
        if matched is not None:
            return matched
    return None


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
        strikes = pd.to_numeric(working[strike_col], errors="coerce")
        spots = pd.to_numeric(working[underlying_col], errors="coerce")
        moneyness_distance = (strikes - spots).abs() / spots
        keep_mask &= (spots > 0) & moneyness_distance.le(settings.max_abs_moneyness_pct)

    bid_col = _find_column(working.columns, ["bid"])
    ask_col = _find_column(working.columns, ["ask"])
    mid_col = _find_column(working.columns, ["mid", "mark", "price", "last", "last_price", "close"])
    if (
        settings.max_bid_ask_spread_pct is not None
        and bid_col is not None
        and ask_col is not None
    ):
        bids = pd.to_numeric(working[bid_col], errors="coerce")
        asks = pd.to_numeric(working[ask_col], errors="coerce")
        mids = (
            pd.to_numeric(working[mid_col], errors="coerce")
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

    return working.loc[keep_mask].reset_index(drop=True)


def apply_spread_quality_filters(
    spreads: pd.DataFrame,
    *,
    settings: OfflineScanQualitySettings,
) -> pd.DataFrame:
    """Filter spread rows that are structurally poor demo/research candidates."""
    if spreads.empty or settings.max_debit_fraction_of_width is None:
        return spreads.copy()

    working = spreads.copy()
    debit_fraction = pd.to_numeric(working["debit"], errors="coerce") / pd.to_numeric(
        working["width"],
        errors="coerce",
    )
    return working.loc[debit_fraction.le(settings.max_debit_fraction_of_width)].reset_index(drop=True)
