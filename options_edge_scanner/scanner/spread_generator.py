"""Utilities for generating canonical vertical spread rows from option quotes."""

from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

from options_edge_scanner.data.provenance import (
    INPUT_PATH_COLUMN,
    PROVENANCE_COLUMNS,
    QUOTE_OBSERVED_AT_COLUMN,
    SNAPSHOT_ID_COLUMN,
    SNAPSHOT_SOURCE_COLUMN,
    SOURCE_METADATA_PATH_COLUMN,
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
)


_OUTPUT_COLUMNS = [
    "ticker",
    "expiration",
    "option_type",
    "spread_type",
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "width",
    "debit",
    "cost",
    "max_profit",
    "max_loss",
    "long_bid",
    "long_ask",
    "long_mid",
    "short_bid",
    "short_ask",
    "short_mid",
    "long_volume",
    "short_volume",
    "long_open_interest",
    "short_open_interest",
    "long_delta",
    "short_delta",
    "implied_volatility",
    "underlying_price",
    SNAPSHOT_ID_COLUMN,
    SNAPSHOT_SOURCE_COLUMN,
    QUOTE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
    INPUT_PATH_COLUMN,
    SOURCE_METADATA_PATH_COLUMN,
]


def _find_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    """Return the first matching column name (case-insensitive)."""
    normalized_map = {str(col).lower(): col for col in columns}
    for candidate in candidates:
        matched = normalized_map.get(candidate.lower())
        if matched is not None:
            return matched
    return None


def _resolve_price_column(df: pd.DataFrame) -> str | None:
    """Choose the best available price-like column."""
    return _find_column(
        df.columns,
        [
            "mid",
            "mark",
            "price",
            "last",
            "last_price",
            "lastprice",
            "close",
        ],
    )


def _resolve_underlying_column(df: pd.DataFrame) -> str | None:
    """Choose the best available underlying spot column."""
    return _find_column(
        df.columns,
        [
            "underlying_price",
            "spot_price",
            "spot",
            "stock_price",
            "underlying",
        ],
    )


def _resolve_iv_column(df: pd.DataFrame) -> str | None:
    """Choose the best available implied-volatility column."""
    return _find_column(
        df.columns,
        [
            "implied_volatility",
            "implied_vol",
            "iv",
        ],
    )


def _normalize_option_type(series: pd.Series) -> pd.Series:
    """Map option type labels to lowercase call/put tokens."""
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.replace({"c": "call", "p": "put"})


def _optional_numeric_value(row: pd.Series, column: str | None) -> float:
    """Return one optional numeric scalar from a row or NaN when unavailable."""
    if column is None:
        return float("nan")
    return float(pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0])


def _resolve_group_value(
    group_keys: object,
    grouping_columns: list[str],
) -> dict[str, object]:
    """Return one mapping of grouping column names to key values."""
    if isinstance(group_keys, tuple):
        values = list(group_keys)
    else:
        values = [group_keys]
    return dict(zip(grouping_columns, values, strict=False))


def _resolve_consistent_underlying_price(values: pd.Series) -> float:
    """Return one consistent underlying price or NaN when unavailable."""
    finite = pd.to_numeric(values, errors="coerce").dropna()
    if finite.empty:
        return float("nan")

    if math.fabs(float(finite.max()) - float(finite.min())) > 1e-9:
        raise ValueError("Spread legs must share a consistent underlying_price snapshot.")

    return float(finite.iloc[0])


def _resolve_provenance_values(leg_rows: pd.DataFrame) -> dict[str, object]:
    """Return one consistent provenance payload for two spread legs."""
    resolved: dict[str, object] = {}
    for column in PROVENANCE_COLUMNS:
        if column not in leg_rows.columns:
            continue

        if column in {QUOTE_OBSERVED_AT_COLUMN, UNDERLYING_PRICE_OBSERVED_AT_COLUMN}:
            timestamps = pd.to_datetime(leg_rows[column], errors="coerce")
            valid = timestamps.dropna()
            if valid.empty:
                resolved[column] = pd.NaT
                continue
            unique = valid.dt.strftime("%Y-%m-%dT%H:%M:%S").unique().tolist()
            if len(unique) > 1:
                raise ValueError(f"Spread legs must share a consistent {column} value.")
            resolved[column] = valid.iloc[0]
            continue

        values = (
            leg_rows[column]
            .dropna()
            .astype("string")
            .str.strip()
        )
        values = values.loc[values.ne("")]
        unique_values = values.unique().tolist()
        if not unique_values:
            resolved[column] = pd.NA
            continue
        if len(unique_values) > 1:
            raise ValueError(f"Spread legs must share a consistent {column} value.")
        resolved[column] = unique_values[0]

    return resolved


def generate_vertical_spreads(option_df: pd.DataFrame) -> pd.DataFrame:
    """Generate valid same-expiration debit vertical spreads from option quotes.

    Produces canonical spread rows for:
    - ``bull_call_debit``: long lower-strike call / short upper-strike call
    - ``bear_put_debit``: long upper-strike put / short lower-strike put
    """
    if option_df.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    strike_col = _find_column(option_df.columns, ["strike", "strike_price", "strikeprice"])
    expiry_col = _find_column(
        option_df.columns,
        ["expiration", "expiry", "expiration_date", "expirationdate", "expiry_date"],
    )
    option_type_col = _find_column(
        option_df.columns,
        ["option_type", "type", "right", "contract_type"],
    )

    if strike_col is None or expiry_col is None or option_type_col is None:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    # Prefer true underlying identifiers; avoid contract-level symbols.
    ticker_col = _find_column(option_df.columns, ["ticker", "underlying", "underlying_symbol"])

    price_col = _resolve_price_column(option_df)
    underlying_col = _resolve_underlying_column(option_df)
    iv_col = _resolve_iv_column(option_df)
    bid_col = _find_column(option_df.columns, ["bid"])
    ask_col = _find_column(option_df.columns, ["ask"])
    volume_col = _find_column(option_df.columns, ["volume"])
    open_interest_col = _find_column(option_df.columns, ["open_interest", "openinterest", "oi"])
    delta_col = _find_column(option_df.columns, ["delta"])
    if price_col is None:
        # Fall back to midpoint if bid/ask are available.
        if bid_col is None or ask_col is None:
            return pd.DataFrame(columns=_OUTPUT_COLUMNS)
        working = option_df.copy()
        working["_price"] = (
            pd.to_numeric(working[bid_col], errors="coerce")
            + pd.to_numeric(working[ask_col], errors="coerce")
        ) / 2
        price_col = "_price"
    else:
        working = option_df.copy()

    working[strike_col] = pd.to_numeric(working[strike_col], errors="coerce")
    working[price_col] = pd.to_numeric(working[price_col], errors="coerce")
    if bid_col is not None:
        working[bid_col] = pd.to_numeric(working[bid_col], errors="coerce")
    if ask_col is not None:
        working[ask_col] = pd.to_numeric(working[ask_col], errors="coerce")
    if volume_col is not None:
        working[volume_col] = pd.to_numeric(working[volume_col], errors="coerce")
    if open_interest_col is not None:
        working[open_interest_col] = pd.to_numeric(working[open_interest_col], errors="coerce")
    if delta_col is not None:
        working[delta_col] = pd.to_numeric(working[delta_col], errors="coerce")
    if underlying_col is not None:
        working[underlying_col] = pd.to_numeric(working[underlying_col], errors="coerce")
    if iv_col is not None:
        working[iv_col] = pd.to_numeric(working[iv_col], errors="coerce")
    working[option_type_col] = _normalize_option_type(working[option_type_col])

    working = working.dropna(subset=[strike_col, expiry_col, option_type_col, price_col])
    if working.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    spreads: list[dict[str, float | str]] = []

    grouping_columns = [expiry_col]
    if ticker_col is not None:
        grouping_columns.insert(0, ticker_col)
    for provenance_group_column in PROVENANCE_COLUMNS:
        if (
            provenance_group_column in working.columns
            and provenance_group_column not in grouping_columns
        ):
            grouping_columns.append(provenance_group_column)

    for group_keys, chain_group in working.groupby(grouping_columns, dropna=False):
        group_lookup = _resolve_group_value(group_keys, grouping_columns)
        ticker_value = group_lookup.get(ticker_col) if ticker_col is not None else None
        expiry_value = group_lookup[expiry_col]

        for side in ("call", "put"):
            side_group = chain_group[chain_group[option_type_col] == side].sort_values(strike_col)
            if len(side_group) < 2:
                continue

            strikes = side_group[strike_col].tolist()
            prices = side_group[price_col].tolist()
            n = len(side_group)

            for i in range(n - 1):
                for j in range(i + 1, n):
                    strike_lower = float(strikes[i])
                    strike_upper = float(strikes[j])
                    width = strike_upper - strike_lower

                    if width <= 0 or width > 10:
                        continue

                    price_lower = float(prices[i])
                    price_upper = float(prices[j])
                    leg_rows = side_group.iloc[[i, j]].copy()
                    iv_values = leg_rows[iv_col] if iv_col is not None else pd.Series(dtype=float)
                    underlying_values = (
                        leg_rows[underlying_col]
                        if underlying_col is not None
                        else pd.Series(dtype=float)
                    )
                    implied_volatility = float(pd.to_numeric(iv_values, errors="coerce").mean())
                    try:
                        underlying_price = _resolve_consistent_underlying_price(underlying_values)
                        provenance_values = _resolve_provenance_values(leg_rows)
                    except ValueError:
                        continue

                    if side == "call":
                        debit = price_lower - price_upper
                        spread_type = "bull_call_debit"
                        long_strike = strike_lower
                        short_strike = strike_upper
                        long_leg_row = side_group.iloc[i]
                        short_leg_row = side_group.iloc[j]
                    else:
                        # Put debit spread: long higher strike put, short lower strike put.
                        debit = price_upper - price_lower
                        spread_type = "bear_put_debit"
                        long_strike = strike_upper
                        short_strike = strike_lower
                        long_leg_row = side_group.iloc[j]
                        short_leg_row = side_group.iloc[i]

                    if debit <= 0 or debit >= width:
                        # Invalid/zero-profit or negative-credit structure.
                        continue

                    max_profit = width - debit
                    if max_profit <= 0:
                        continue

                    spreads.append(
                        {
                            "ticker": ticker_value,
                            "expiration": expiry_value,
                            "option_type": side,
                            "spread_type": spread_type,
                            "lower_strike": strike_lower,
                            "upper_strike": strike_upper,
                            "long_strike": float(long_strike),
                            "short_strike": float(short_strike),
                            "debit": float(debit),
                            "cost": float(debit),
                            "max_profit": float(max_profit),
                            "max_loss": float(debit),
                            "width": float(width),
                            "long_bid": _optional_numeric_value(long_leg_row, bid_col),
                            "long_ask": _optional_numeric_value(long_leg_row, ask_col),
                            "long_mid": _optional_numeric_value(long_leg_row, price_col),
                            "short_bid": _optional_numeric_value(short_leg_row, bid_col),
                            "short_ask": _optional_numeric_value(short_leg_row, ask_col),
                            "short_mid": _optional_numeric_value(short_leg_row, price_col),
                            "long_volume": _optional_numeric_value(long_leg_row, volume_col),
                            "short_volume": _optional_numeric_value(short_leg_row, volume_col),
                            "long_open_interest": _optional_numeric_value(long_leg_row, open_interest_col),
                            "short_open_interest": _optional_numeric_value(short_leg_row, open_interest_col),
                            "long_delta": _optional_numeric_value(long_leg_row, delta_col),
                            "short_delta": _optional_numeric_value(short_leg_row, delta_col),
                            "implied_volatility": implied_volatility,
                            "underlying_price": underlying_price,
                            **provenance_values,
                        }
                    )

    if not spreads:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    return pd.DataFrame(spreads, columns=_OUTPUT_COLUMNS)
