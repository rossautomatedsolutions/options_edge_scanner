"""Deterministic scanner orchestration for research-only opportunity ranking."""

from __future__ import annotations

from typing import Any

import pandas as pd

from options_edge_scanner.config import ScannerConfig
from options_edge_scanner.models.probability_estimator import estimate_probability_of_profit
from options_edge_scanner.models.spread_ev_calculator import calculate_expected_value
from options_edge_scanner.scanner.opportunity_ranker import rank_spreads
from options_edge_scanner.scanner.quality_filters import (
    OfflineScanQualitySettings,
    apply_option_quote_quality_filters,
    apply_spread_quality_filters,
)
from options_edge_scanner.scanner.spread_generator import generate_vertical_spreads


SCANNER_OUTPUT_COLUMNS = [
    "ticker",
    "expiration",
    "days_to_expiration",
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
    "underlying_price",
    "implied_volatility",
    "probability_of_profit",
    "probability",
    "prob_loss",
    "expected_value",
    "EV",
    "edge_pct",
    "ev_method",
    "avg_profit",
    "avg_loss",
]


def _normalize_as_of(as_of: Any | None) -> pd.Timestamp:
    """Resolve a deterministic as-of date for DTE calculations."""
    if as_of is None:
        return pd.Timestamp.utcnow().tz_localize(None).normalize()
    return pd.Timestamp(as_of).tz_localize(None).normalize()


def _empty_scanner_frame() -> pd.DataFrame:
    """Return an empty scanner-output dataframe with canonical columns."""
    return pd.DataFrame(columns=SCANNER_OUTPUT_COLUMNS)


def build_scanner_opportunities(
    option_quotes: pd.DataFrame,
    *,
    as_of: Any | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
) -> pd.DataFrame:
    """Build ranked scanner opportunities from normalized option quote rows."""
    settings = quality_settings or OfflineScanQualitySettings()
    filtered_quotes = apply_option_quote_quality_filters(option_quotes, settings=settings)
    spreads = generate_vertical_spreads(filtered_quotes)
    spreads = apply_spread_quality_filters(spreads, settings=settings)
    if spreads.empty:
        return _empty_scanner_frame()

    working = spreads.copy()
    working["expiration"] = pd.to_datetime(working["expiration"], errors="coerce")
    as_of_ts = _normalize_as_of(as_of)
    working["days_to_expiration"] = (
        working["expiration"].dt.normalize() - as_of_ts
    ).dt.days.astype(float)
    working = working.loc[working["days_to_expiration"] > 0].copy()
    if working.empty:
        return _empty_scanner_frame()

    opportunity_rows: list[dict[str, Any]] = []
    for spread_row in working.to_dict("records"):
        probability = estimate_probability_of_profit(spread_row)
        ev_result = calculate_expected_value(
            spread_row,
            probability_weights={"win": probability, "loss": 1.0 - probability},
        )

        combined = dict(spread_row)
        combined.update(ev_result)
        combined["probability_of_profit"] = float(probability)
        combined["probability"] = float(probability)
        combined["prob_loss"] = float(1.0 - probability)
        combined["EV"] = float(ev_result["expected_value"])
        opportunity_rows.append(combined)

    if not opportunity_rows:
        return _empty_scanner_frame()

    opportunities = pd.DataFrame(opportunity_rows)
    ranked = rank_spreads(opportunities)

    for column in SCANNER_OUTPUT_COLUMNS:
        if column not in ranked.columns:
            ranked[column] = pd.NA

    return ranked[SCANNER_OUTPUT_COLUMNS].reset_index(drop=True)


def run_scan(config: ScannerConfig) -> pd.DataFrame:
    """Placeholder config-driven entrypoint for the future scanner workflow."""
    _ = config
    return _empty_scanner_frame()
