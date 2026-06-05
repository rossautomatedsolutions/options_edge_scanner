"""Utilities for generating canonical vertical spread rows from option quotes."""

from __future__ import annotations

from typing import Iterable

import pandas as pd


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
    "implied_volatility",
    "underlying_price",
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
    if price_col is None:
        # Fall back to midpoint if bid/ask are available.
        bid_col = _find_column(option_df.columns, ["bid"])
        ask_col = _find_column(option_df.columns, ["ask"])
        if bid_col is None or ask_col is None:
            return pd.DataFrame(columns=_OUTPUT_COLUMNS)
        working = option_df.copy()
        working["_price"] = (pd.to_numeric(working[bid_col], errors="coerce") + pd.to_numeric(working[ask_col], errors="coerce")) / 2
        price_col = "_price"
    else:
        working = option_df.copy()

    working[strike_col] = pd.to_numeric(working[strike_col], errors="coerce")
    working[price_col] = pd.to_numeric(working[price_col], errors="coerce")
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

    for group_keys, chain_group in working.groupby(grouping_columns, dropna=False):
        if ticker_col is None:
            ticker_value = None
            expiry_value = group_keys
        else:
            ticker_value, expiry_value = group_keys

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
                    iv_values = side_group.iloc[[i, j]][iv_col] if iv_col is not None else pd.Series(dtype=float)
                    underlying_values = (
                        side_group.iloc[[i, j]][underlying_col]
                        if underlying_col is not None
                        else pd.Series(dtype=float)
                    )
                    implied_volatility = float(pd.to_numeric(iv_values, errors="coerce").mean())
                    underlying_price = float(pd.to_numeric(underlying_values, errors="coerce").mean())

                    if side == "call":
                        debit = price_lower - price_upper
                        spread_type = "bull_call_debit"
                        long_strike = strike_lower
                        short_strike = strike_upper
                    else:
                        # Put debit spread: long higher strike put, short lower strike put.
                        debit = price_upper - price_lower
                        spread_type = "bear_put_debit"
                        long_strike = strike_upper
                        short_strike = strike_lower

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
                            "implied_volatility": implied_volatility,
                            "underlying_price": underlying_price,
                        }
                    )

    if not spreads:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    return pd.DataFrame(spreads, columns=_OUTPUT_COLUMNS)
