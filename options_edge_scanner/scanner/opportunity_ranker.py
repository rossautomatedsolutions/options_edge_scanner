"""Ranking utilities for spread opportunities."""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = ("EV", "probability", "expected_value", "edge_pct")


def rank_spreads(spread_df: pd.DataFrame) -> pd.DataFrame:
    """Filter and rank spread opportunities.

    Rules:
    - Keep only rows where ``EV > 0`` and ``probability > 0.3``.
    - Rank using ``expected_value`` and then ``edge_pct`` in descending order.
    - Return only the top 20 opportunities.
    """
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in spread_df.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required columns: {missing}")

    ranked_df = (
        spread_df.loc[(spread_df["EV"] > 0) & (spread_df["probability"] > 0.3)]
        .sort_values(["expected_value", "edge_pct"], ascending=[False, False])
        .head(20)
        .copy()
    )

    return ranked_df
