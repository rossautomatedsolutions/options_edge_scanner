"""Deterministic scanner orchestration for research-only opportunity ranking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from options_edge_scanner.config import ScannerConfig
from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.data.provenance import (
    INPUT_PATH_COLUMN,
    QUOTE_OBSERVED_AT_COLUMN,
    SNAPSHOT_ID_COLUMN,
    SNAPSHOT_SOURCE_COLUMN,
    SOURCE_METADATA_PATH_COLUMN,
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
    enrich_option_quote_provenance,
    normalize_provenance_columns,
    resolve_effective_as_of,
    validate_point_in_time_integrity,
)
from options_edge_scanner.models.probability_models import predict_spread_probability
from options_edge_scanner.models.spread_ev_calculator import calculate_expected_value
from options_edge_scanner.scanner.execution import apply_execution_adjustments
from options_edge_scanner.scanner.opportunity_ranker import rank_spreads
from options_edge_scanner.scanner.quality_filters import (
    OfflineScanQualitySettings,
    apply_option_quote_quality_filters,
    apply_spread_quality_filters,
)
from options_edge_scanner.scanner.spread_generator import generate_vertical_spreads


@dataclass(frozen=True)
class ScannerBuildArtifacts:
    """Structured scanner outputs plus deterministic row-count diagnostics."""

    opportunities: pd.DataFrame
    as_of: pd.Timestamp
    prepared_quote_count: int
    filtered_quote_count: int
    generated_spread_count: int
    filtered_spread_count: int
    dte_eligible_spread_count: int
    ranked_candidate_count: int


SCANNER_OUTPUT_COLUMNS = [
    "ticker",
    "expiration",
    "as_of",
    SNAPSHOT_ID_COLUMN,
    SNAPSHOT_SOURCE_COLUMN,
    QUOTE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
    INPUT_PATH_COLUMN,
    SOURCE_METADATA_PATH_COLUMN,
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
    "quoted_debit",
    "quoted_cost",
    "quoted_max_profit",
    "quoted_max_loss",
    "theoretical_expected_value",
    "theoretical_edge_pct",
    "theoretical_ev_method",
    "long_bid",
    "long_ask",
    "long_mid",
    "short_bid",
    "short_ask",
    "short_mid",
    "spread_bid",
    "spread_ask",
    "spread_market_width",
    "entry_slippage",
    "entry_slippage_pct",
    "entry_fill_fraction_of_market_width",
    "entry_price_policy",
    "liquidity_score",
    "leg_relative_spread_mean",
    "long_volume",
    "short_volume",
    "spread_min_volume",
    "long_open_interest",
    "short_open_interest",
    "spread_min_open_interest",
    "long_delta",
    "short_delta",
    "underlying_price",
    "implied_volatility",
    "probability_model_name",
    "probability_model_version",
    "predicted_event_name",
    "predicted_event_direction",
    "predicted_event_operator",
    "predicted_event_threshold",
    "predicted_event_horizon",
    "probability_of_profit",
    "probability",
    "prob_loss",
    "expected_value",
    "EV",
    "edge_pct",
    "ev_method",
    "avg_profit",
    "avg_loss",
    "ranking_score",
    "selection_rank",
]


def _normalize_as_of(as_of: Any | None) -> pd.Timestamp:
    """Resolve a deterministic as-of date for DTE calculations."""
    if as_of is None:
        return pd.Timestamp.utcnow().tz_localize(None).normalize()
    return pd.Timestamp(as_of).tz_localize(None).normalize()


def _empty_scanner_frame() -> pd.DataFrame:
    """Return an empty scanner-output dataframe with canonical columns."""
    return pd.DataFrame(columns=SCANNER_OUTPUT_COLUMNS)


def build_scanner_artifacts(
    option_quotes: pd.DataFrame,
    *,
    as_of: Any | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
    allow_unsafe_as_of: bool = False,
) -> ScannerBuildArtifacts:
    """Build ranked scanner opportunities plus deterministic diagnostics."""
    settings = quality_settings or OfflineScanQualitySettings()
    prepared_quotes = normalize_provenance_columns(option_quotes)
    as_of_ts, as_of_day_precision = resolve_effective_as_of(
        prepared_quotes,
        explicit_as_of=as_of,
    )
    prepared_quotes = validate_point_in_time_integrity(
        prepared_quotes,
        as_of=as_of_ts,
        as_of_day_precision=as_of_day_precision,
        allow_unsafe_as_of=allow_unsafe_as_of,
    )
    prepared_quote_count = int(len(prepared_quotes))
    filtered_quotes = apply_option_quote_quality_filters(prepared_quotes, settings=settings)
    filtered_quote_count = int(len(filtered_quotes))
    spreads = generate_vertical_spreads(filtered_quotes)
    generated_spread_count = int(len(spreads))
    spreads = apply_execution_adjustments(spreads, settings=settings)
    spreads = apply_spread_quality_filters(spreads, settings=settings)
    filtered_spread_count = int(len(spreads))
    if spreads.empty:
        return ScannerBuildArtifacts(
            opportunities=_empty_scanner_frame(),
            as_of=as_of_ts,
            prepared_quote_count=prepared_quote_count,
            filtered_quote_count=filtered_quote_count,
            generated_spread_count=generated_spread_count,
            filtered_spread_count=filtered_spread_count,
            dte_eligible_spread_count=0,
            ranked_candidate_count=0,
        )

    working = spreads.copy()
    working["expiration"] = pd.to_datetime(working["expiration"], errors="coerce")
    working["days_to_expiration"] = (
        working["expiration"].dt.normalize() - as_of_ts.normalize()
    ).dt.days.astype(float)
    working = working.loc[working["days_to_expiration"] > 0].copy()
    dte_eligible_spread_count = int(len(working))
    if working.empty:
        return ScannerBuildArtifacts(
            opportunities=_empty_scanner_frame(),
            as_of=as_of_ts,
            prepared_quote_count=prepared_quote_count,
            filtered_quote_count=filtered_quote_count,
            generated_spread_count=generated_spread_count,
            filtered_spread_count=filtered_spread_count,
            dte_eligible_spread_count=dte_eligible_spread_count,
            ranked_candidate_count=0,
        )

    opportunity_rows: list[dict[str, Any]] = []
    for spread_row in working.to_dict("records"):
        probability_prediction = predict_spread_probability(spread_row)
        probability = probability_prediction.probability
        theoretical_spread_row = dict(spread_row)
        theoretical_spread_row["debit"] = theoretical_spread_row.get("quoted_debit", spread_row["debit"])
        theoretical_spread_row["cost"] = theoretical_spread_row.get("quoted_cost", spread_row["cost"])
        theoretical_spread_row["max_profit"] = theoretical_spread_row.get(
            "quoted_max_profit",
            spread_row["max_profit"],
        )
        theoretical_spread_row["max_loss"] = theoretical_spread_row.get(
            "quoted_max_loss",
            spread_row["max_loss"],
        )
        theoretical_ev_result = calculate_expected_value(theoretical_spread_row)
        ev_result = calculate_expected_value(spread_row)

        combined = dict(spread_row)
        combined.update(ev_result)
        combined["theoretical_expected_value"] = float(theoretical_ev_result["expected_value"])
        combined["theoretical_edge_pct"] = float(theoretical_ev_result["edge_pct"])
        combined["theoretical_ev_method"] = str(theoretical_ev_result["ev_method"])
        combined["as_of"] = as_of_ts
        combined["probability_model_name"] = probability_prediction.probability_model_name
        combined["probability_model_version"] = probability_prediction.probability_model_version
        combined["predicted_event_name"] = probability_prediction.predicted_event_name
        combined["predicted_event_direction"] = probability_prediction.predicted_event_direction
        combined["predicted_event_operator"] = probability_prediction.predicted_event_operator
        combined["predicted_event_threshold"] = float(
            probability_prediction.predicted_event_threshold
        )
        combined["predicted_event_horizon"] = probability_prediction.predicted_event_horizon
        combined["probability_of_profit"] = float(probability)
        combined["probability"] = float(probability)
        combined["prob_loss"] = float(1.0 - probability)
        combined["EV"] = float(ev_result["expected_value"])
        opportunity_rows.append(combined)

    if not opportunity_rows:
        return ScannerBuildArtifacts(
            opportunities=_empty_scanner_frame(),
            as_of=as_of_ts,
            prepared_quote_count=prepared_quote_count,
            filtered_quote_count=filtered_quote_count,
            generated_spread_count=generated_spread_count,
            filtered_spread_count=filtered_spread_count,
            dte_eligible_spread_count=dte_eligible_spread_count,
            ranked_candidate_count=0,
        )

    opportunities = pd.DataFrame(opportunity_rows)
    ranked = rank_spreads(opportunities, settings=settings)

    for column in SCANNER_OUTPUT_COLUMNS:
        if column not in ranked.columns:
            ranked[column] = pd.NA

    final_opportunities = ranked[SCANNER_OUTPUT_COLUMNS].reset_index(drop=True)
    return ScannerBuildArtifacts(
        opportunities=final_opportunities,
        as_of=as_of_ts,
        prepared_quote_count=prepared_quote_count,
        filtered_quote_count=filtered_quote_count,
        generated_spread_count=generated_spread_count,
        filtered_spread_count=filtered_spread_count,
        dte_eligible_spread_count=dte_eligible_spread_count,
        ranked_candidate_count=int(len(final_opportunities)),
    )


def build_scanner_opportunities(
    option_quotes: pd.DataFrame,
    *,
    as_of: Any | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
    allow_unsafe_as_of: bool = False,
) -> pd.DataFrame:
    """Build ranked scanner opportunities from normalized option quote rows."""
    artifacts = build_scanner_artifacts(
        option_quotes,
        as_of=as_of,
        quality_settings=quality_settings,
        allow_unsafe_as_of=allow_unsafe_as_of,
    )
    return artifacts.opportunities.copy()


def run_scan(config: ScannerConfig) -> pd.DataFrame:
    """Run the maintained offline scanner from one config object."""
    input_path = Path(config.input_path)
    if not str(input_path).strip():
        raise ValueError("ScannerConfig.input_path is required.")

    option_quotes = load_option_quotes(input_path, require_underlying_price=config.spot is None)
    option_quotes = enrich_option_quote_provenance(option_quotes, input_path=input_path)

    if config.spot is not None:
        option_quotes["underlying_price"] = float(config.spot)
        option_quotes["underlying_price_source"] = (
            str(config.spot_source).strip()
            if config.spot_source is not None and str(config.spot_source).strip()
            else "config.override"
        )
        if config.spot_observed_at is None:
            option_quotes["underlying_price_observed_at"] = pd.NaT
            if not config.allow_unsafe_as_of:
                raise ValueError(
                    "ScannerConfig.spot requires spot_observed_at for safe provenance, "
                    "or allow_unsafe_as_of=True."
                )
        else:
            parsed_spot_observed_at = pd.to_datetime(
                config.spot_observed_at,
                errors="coerce",
                utc=True,
            )
            if pd.isna(parsed_spot_observed_at):
                raise ValueError("ScannerConfig.spot_observed_at must be a valid timestamp.")
            option_quotes["underlying_price_observed_at"] = pd.Timestamp(
                parsed_spot_observed_at
            ).tz_localize(None)

    artifacts = build_scanner_artifacts(
        option_quotes,
        as_of=config.as_of,
        quality_settings=config.quality_settings,
        allow_unsafe_as_of=config.allow_unsafe_as_of,
    )
    opportunities = artifacts.opportunities.copy()

    if config.output_path is not None:
        output_path = Path(config.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        opportunities.to_csv(output_path, index=False)
    else:
        output_path = Path("<memory>")

    if config.report_output_path is not None:
        from options_edge_scanner.scanner.reporting import build_scan_report, write_scan_report

        report = build_scan_report(
            artifacts,
            input_path=input_path,
            output_path=output_path,
            settings=config.quality_settings,
            mode="run_scan_config",
        )
        write_scan_report(report, config.report_output_path)

    return opportunities
