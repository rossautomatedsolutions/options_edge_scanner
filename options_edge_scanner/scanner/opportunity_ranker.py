"""Ranking utilities for scanner opportunities."""

from __future__ import annotations

import pandas as pd

from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


REQUIRED_COLUMNS = ("expected_value", "edge_pct")


def _resolve_probability_column(spread_df: pd.DataFrame) -> str:
    """Return the probability-like column used by maintained ranking."""
    if "probability_of_profit" in spread_df.columns:
        return "probability_of_profit"
    if "probability" in spread_df.columns:
        return "probability"
    raise ValueError("Missing required columns: probability_of_profit or probability")


def _expiration_bucket_key(value: object) -> str:
    """Return one stable bucket key for expiration-level concentration limits."""
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).isoformat()


def rank_spreads(
    spread_df: pd.DataFrame,
    *,
    settings: OfflineScanQualitySettings | None = None,
) -> pd.DataFrame:
    """Filter and rank spread opportunities.

    Rules:
    - Keep only rows above the configured EV and probability thresholds.
    - Prefer execution-adjusted rows with stronger liquidity via ``ranking_score``.
    - Optionally cap concentration by ticker and expiration.
    - Return only the configured top-N opportunities.
    """
    active_settings = settings or OfflineScanQualitySettings()
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in spread_df.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required columns: {missing}")

    probability_column = _resolve_probability_column(spread_df)

    working = spread_df.copy()
    if "EV" not in working.columns:
        working["EV"] = working["expected_value"]
    if "probability" not in working.columns:
        working["probability"] = working[probability_column]
    if "liquidity_score" not in working.columns:
        working["liquidity_score"] = 0.5

    working["expected_value"] = pd.to_numeric(working["expected_value"], errors="coerce")
    working["edge_pct"] = pd.to_numeric(working["edge_pct"], errors="coerce")
    working["probability"] = pd.to_numeric(working["probability"], errors="coerce")
    working["liquidity_score"] = pd.to_numeric(working["liquidity_score"], errors="coerce").fillna(0.5)
    working["ranking_score"] = working["expected_value"] * (0.5 + (0.5 * working["liquidity_score"]))

    ranked_candidates = working.loc[
        (working["expected_value"] > float(active_settings.min_expected_value))
        & (working["probability"] > float(active_settings.min_probability_of_profit))
    ].sort_values(
        [
            "ranking_score",
            "expected_value",
            "edge_pct",
            "probability",
            "liquidity_score",
            "ticker",
            "expiration",
            "spread_type",
            "lower_strike",
            "upper_strike",
        ],
        ascending=[False, False, False, False, False, True, True, True, True, True],
        kind="stable",
    )

    top_n = max(int(active_settings.top_n), 0)
    if top_n == 0 or ranked_candidates.empty:
        return ranked_candidates.iloc[0:0].copy()

    if (
        active_settings.max_positions_per_ticker is None
        and active_settings.max_positions_per_expiration is None
    ):
        ranked_df = ranked_candidates.head(top_n).copy()
        ranked_df["selection_rank"] = range(1, len(ranked_df) + 1)
        return ranked_df

    ticker_counts: dict[str, int] = {}
    expiration_counts: dict[str, int] = {}
    selected_indices: list[object] = []

    for row in ranked_candidates.itertuples():
        ticker_key = str(getattr(row, "ticker", "") or "")
        expiration_key = _expiration_bucket_key(getattr(row, "expiration", None))

        if (
            active_settings.max_positions_per_ticker is not None
            and ticker_counts.get(ticker_key, 0) >= active_settings.max_positions_per_ticker
        ):
            continue
        if (
            active_settings.max_positions_per_expiration is not None
            and expiration_counts.get(expiration_key, 0) >= active_settings.max_positions_per_expiration
        ):
            continue

        selected_indices.append(row.Index)
        ticker_counts[ticker_key] = ticker_counts.get(ticker_key, 0) + 1
        expiration_counts[expiration_key] = expiration_counts.get(expiration_key, 0) + 1

        if len(selected_indices) >= top_n:
            break

    ranked_df = ranked_candidates.loc[selected_indices].copy()
    ranked_df["selection_rank"] = range(1, len(ranked_df) + 1)
    return ranked_df
