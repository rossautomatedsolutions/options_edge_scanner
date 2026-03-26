"""Utilities for generating vertical option spreads from option-chain data."""

from __future__ import annotations

from typing import Iterable

import pandas as pd


_OUTPUT_COLUMNS = [
    "ticker",
    "expiration",
    "spread_type",
    "strike_lower",
    "strike_upper",
    "cost",
    "max_profit",
    "width",
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


def _normalize_option_type(series: pd.Series) -> pd.Series:
    """Map option type labels to lowercase call/put tokens."""
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.replace({"c": "call", "p": "put"})


def generate_vertical_spreads(option_df: pd.DataFrame) -> pd.DataFrame:
    """Generate valid same-expiration vertical spreads from option-chain rows.

    Produces call debit spreads (long lower strike / short upper strike)
    and put debit spreads (long upper strike / short lower strike).
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

    ticker_col = _find_column(option_df.columns, ["ticker", "symbol", "underlying", "underlying_symbol"])

    price_col = _resolve_price_column(option_df)
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
    working[option_type_col] = _normalize_option_type(working[option_type_col])

    working = working.dropna(subset=[strike_col, expiry_col, option_type_col, price_col])
    if working.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    spreads: list[dict[str, float | str]] = []

    grouping_columns = [expiry_col]
    if ticker_col is not None:
        grouping_columns.insert(0, ticker_col)

    for group_keys, chain_group in working.groupby(grouping_columns):
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

                    if side == "call":
                        cost = price_lower - price_upper
                        spread_type = "call_vertical"
                    else:
                        # Put debit spread: long higher strike put, short lower strike put.
                        cost = price_upper - price_lower
                        spread_type = "put_vertical"

                    if cost <= 0 or cost >= width:
                        # Invalid/zero-profit or negative-credit structure.
                        continue

                    max_profit = width - cost
                    if max_profit <= 0:
                        continue

                    spreads.append(
                        {
                            "ticker": ticker_value,
                            "expiration": expiry_value,
                            "spread_type": spread_type,
                            "strike_lower": strike_lower,
                            "strike_upper": strike_upper,
                            "cost": float(cost),
                            "max_profit": float(max_profit),
                            "width": float(width),
                        }
                    )

    if not spreads:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    return pd.DataFrame(spreads, columns=_OUTPUT_COLUMNS)
