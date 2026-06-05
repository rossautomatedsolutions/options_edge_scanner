"""Ranking utilities for scanner opportunities."""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = ("expected_value", "edge_pct")


def rank_spreads(spread_df: pd.DataFrame) -> pd.DataFrame:
    """Filter and rank spread opportunities.

    Rules:
    - Keep only rows where expected value is positive.
    - Keep only rows where probability of profit is above 0.3.
    - Rank using ``expected_value`` and then ``edge_pct`` in descending order.
    - Return only the top 20 opportunities.
    """
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in spread_df.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required columns: {missing}")

    probability_column = (
        "probability_of_profit"
        if "probability_of_profit" in spread_df.columns
        else "probability"
        if "probability" in spread_df.columns
        else None
    )
    if probability_column is None:
        raise ValueError("Missing required columns: probability_of_profit or probability")

    working = spread_df.copy()
    if "EV" not in working.columns:
        working["EV"] = working["expected_value"]
    if "probability" not in working.columns:
        working["probability"] = working[probability_column]

    ranked_df = (
        working.loc[(working["expected_value"] > 0) & (working["probability"] > 0.3)]
        .sort_values(["expected_value", "edge_pct"], ascending=[False, False])
        .head(20)
        .copy()
    )

    return ranked_df
