"""Execution-aware spread pricing helpers for offline research scans."""

from __future__ import annotations

import math

import pandas as pd

from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


_DEFAULT_MISSING_SIZE_SCORE = 0.5
_VOLUME_SCORE_REFERENCE = 250.0
_OPEN_INTEREST_SCORE_REFERENCE = 1000.0


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return one numeric series for a frame column or all-NaN when absent."""
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _relative_width(bid: pd.Series, ask: pd.Series, reference: pd.Series) -> pd.Series:
    """Return one relative bid/ask width series against a reference price."""
    width = ask - bid
    relative = width / reference
    valid = bid.ge(0) & ask.ge(bid) & reference.gt(0)
    return relative.where(valid)


def _size_score(size: pd.Series, *, reference: float) -> pd.Series:
    """Return one smooth 0..1 liquidity score from size-like fields."""
    clipped = pd.to_numeric(size, errors="coerce")
    score = pd.Series(_DEFAULT_MISSING_SIZE_SCORE, index=clipped.index, dtype=float)
    valid = clipped.notna() & clipped.ge(0)
    if not valid.any():
        return score

    denominator = math.log1p(reference)
    numerator = clipped.loc[valid].map(lambda value: math.log1p(float(max(value, 0.0))))
    score.loc[valid] = (numerator / denominator).clip(lower=0.0, upper=1.0)
    return score


def apply_execution_adjustments(
    spreads: pd.DataFrame,
    *,
    settings: OfflineScanQualitySettings,
) -> pd.DataFrame:
    """Return spread rows enriched with conservative executable-entry estimates."""
    if spreads.empty:
        return spreads.copy()

    working = spreads.copy()

    quoted_debit = pd.to_numeric(working["debit"], errors="coerce")
    quoted_max_profit = pd.to_numeric(working["max_profit"], errors="coerce")
    quoted_max_loss = pd.to_numeric(working["max_loss"], errors="coerce")
    width = pd.to_numeric(working["width"], errors="coerce")

    long_bid = _numeric_series(working, "long_bid")
    long_ask = _numeric_series(working, "long_ask")
    long_mid = _numeric_series(working, "long_mid")
    short_bid = _numeric_series(working, "short_bid")
    short_ask = _numeric_series(working, "short_ask")
    short_mid = _numeric_series(working, "short_mid")
    long_volume = _numeric_series(working, "long_volume")
    short_volume = _numeric_series(working, "short_volume")
    long_open_interest = _numeric_series(working, "long_open_interest")
    short_open_interest = _numeric_series(working, "short_open_interest")

    spread_bid = long_bid - short_ask
    spread_ask = long_ask - short_bid
    valid_market = spread_bid.ge(0) & spread_ask.gt(0) & spread_ask.ge(spread_bid)
    spread_market_width = (spread_ask - spread_bid).where(valid_market)

    long_relative_spread = _relative_width(long_bid, long_ask, long_mid)
    short_relative_spread = _relative_width(short_bid, short_ask, short_mid)
    leg_relative_spread_mean = pd.concat(
        [long_relative_spread.rename("long"), short_relative_spread.rename("short")],
        axis=1,
    ).mean(axis=1, skipna=True)

    spread_min_volume = pd.concat(
        [long_volume.rename("long"), short_volume.rename("short")],
        axis=1,
    ).min(axis=1, skipna=True)
    spread_min_open_interest = pd.concat(
        [long_open_interest.rename("long"), short_open_interest.rename("short")],
        axis=1,
    ).min(axis=1, skipna=True)

    quote_tightness = 1.0 - (spread_market_width / quoted_debit).clip(lower=0.0, upper=1.0)
    leg_spread_reference = (
        float(settings.max_bid_ask_spread_pct)
        if settings.max_bid_ask_spread_pct is not None and settings.max_bid_ask_spread_pct > 0
        else 1.0
    )
    leg_tightness = 1.0 - (leg_relative_spread_mean / leg_spread_reference).clip(
        lower=0.0,
        upper=1.0,
    )
    volume_score = _size_score(spread_min_volume, reference=_VOLUME_SCORE_REFERENCE)
    open_interest_score = _size_score(
        spread_min_open_interest,
        reference=_OPEN_INTEREST_SCORE_REFERENCE,
    )

    liquidity_components = pd.concat(
        [
            quote_tightness.rename("quote_tightness"),
            leg_tightness.rename("leg_tightness"),
            volume_score.rename("volume_score"),
            open_interest_score.rename("open_interest_score"),
        ],
        axis=1,
    )
    liquidity_score = liquidity_components.mean(axis=1, skipna=True).fillna(0.5).clip(
        lower=0.0,
        upper=1.0,
    )

    floor = max(float(settings.execution_slippage_floor), 0.0)
    cap = max(float(settings.execution_slippage_cap), floor)
    fill_fraction = (floor + ((1.0 - liquidity_score) * (cap - floor))).clip(
        lower=floor,
        upper=cap,
    )

    entry_slippage = spread_market_width.fillna(0.0) * fill_fraction
    execution_debit = quoted_debit.copy()
    if valid_market.any():
        executable_with_penalty = quoted_debit.loc[valid_market] + entry_slippage.loc[valid_market]
        execution_debit.loc[valid_market] = executable_with_penalty.where(
            executable_with_penalty.le(spread_ask.loc[valid_market]),
            spread_ask.loc[valid_market],
        )

    working["quoted_debit"] = quoted_debit
    working["quoted_cost"] = quoted_debit
    working["quoted_max_profit"] = quoted_max_profit
    working["quoted_max_loss"] = quoted_max_loss
    working["spread_bid"] = spread_bid.where(valid_market)
    working["spread_ask"] = spread_ask.where(valid_market)
    working["spread_market_width"] = spread_market_width
    working["spread_min_volume"] = spread_min_volume
    working["spread_min_open_interest"] = spread_min_open_interest
    working["leg_relative_spread_mean"] = leg_relative_spread_mean
    working["liquidity_score"] = liquidity_score
    working["entry_fill_fraction_of_market_width"] = fill_fraction.where(valid_market, 0.0)
    working["entry_slippage"] = entry_slippage
    working["entry_slippage_pct"] = (entry_slippage / quoted_debit).where(quoted_debit.gt(0))
    working["entry_price_policy"] = "quoted_mid_fallback"
    working.loc[valid_market, "entry_price_policy"] = "mid_plus_dynamic_market_width_penalty"
    working["debit"] = execution_debit
    working["cost"] = execution_debit
    working["max_loss"] = execution_debit
    working["max_profit"] = width - execution_debit
    return working
