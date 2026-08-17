"""Probability calibration evaluation helpers for offline research workflows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from options_edge_scanner.calibration.contracts import (
    CALIBRATION_SUMMARY_COLUMNS,
    EVALUATION_OBSERVATION_COLUMNS,
    PREDICTION_OPTIONAL_COLUMNS,
    PREDICTION_REQUIRED_COLUMNS,
    RELIABILITY_BIN_COLUMNS,
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    build_observation_group_id,
    build_prediction_id,
    build_required_outcome_key,
    format_date_like,
    format_utc_timestamp,
    _normalize_string_scalar,
    validate_probability_prediction_frame,
    validate_realized_outcome_frame,
)
from options_edge_scanner.models.probability_estimator import TERMINAL_BREAKEVEN_EVENT_NAME


@dataclass(frozen=True)
class CalibrationEvaluationArtifacts:
    """Machine-readable calibration evaluation outputs plus one text summary."""

    observations: pd.DataFrame
    reliability_bins: pd.DataFrame
    summary: pd.DataFrame
    reliability_summary: str


def _resolve_prediction_timestamp(row: dict[str, Any]) -> pd.Timestamp:
    """Resolve the earliest safe export timestamp for one scanner prediction row."""
    quote_observed_at = pd.to_datetime(row["quote_observed_at"], errors="coerce", utc=True)
    as_of = pd.to_datetime(row["as_of"], errors="coerce", utc=True)
    if pd.isna(quote_observed_at) or pd.isna(as_of):
        raise ValueError("Scanner opportunities must provide valid quote_observed_at and as_of timestamps.")
    return pd.Timestamp(max(quote_observed_at, as_of)).tz_localize(None)


def _resolve_required_snapshot_id(row: dict[str, Any]) -> str:
    """Resolve one non-null snapshot identifier from a scanner opportunity row."""
    snapshot_id = _normalize_string_scalar(row.get("snapshot_id"))
    if snapshot_id is None:
        raise ValueError(
            "Scanner opportunities must provide a non-empty snapshot_id before probability export."
        )
    return snapshot_id


def export_scanner_probability_predictions(opportunities: pd.DataFrame) -> pd.DataFrame:
    """Project scanner opportunities into the calibration prediction contract."""
    required_columns = {
        "ticker",
        "snapshot_id",
        "quote_observed_at",
        "as_of",
        "expiration",
        "spread_type",
        "lower_strike",
        "upper_strike",
        "long_strike",
        "short_strike",
        "probability_of_profit",
        "probability_model_name",
        "probability_model_version",
        "predicted_event_name",
        "predicted_event_direction",
        "predicted_event_operator",
        "predicted_event_threshold",
        "predicted_event_horizon",
    }
    missing_columns = sorted(required_columns.difference(opportunities.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Scanner opportunities are missing calibration export columns: {missing}")

    records: list[dict[str, Any]] = []
    optional_columns = [column for column in PREDICTION_OPTIONAL_COLUMNS if column in opportunities.columns]
    for row in opportunities.to_dict("records"):
        prediction_timestamp = _resolve_prediction_timestamp(row)
        snapshot_id = _resolve_required_snapshot_id(row)
        observation_group_id = build_observation_group_id(
            snapshot_id=snapshot_id,
            ticker=str(row["ticker"]),
            prediction_timestamp=prediction_timestamp,
            expiration=row["expiration"],
        )
        prediction_id = build_prediction_id(
            observation_group_id=observation_group_id,
            spread_type=str(row["spread_type"]),
            lower_strike=row["lower_strike"],
            upper_strike=row["upper_strike"],
            probability_model_name=str(row["probability_model_name"]),
            probability_model_version=str(row["probability_model_version"]),
        )
        exported = {
            "prediction_id": prediction_id,
            "snapshot_id": snapshot_id,
            "ticker": str(row["ticker"]).strip().upper(),
            "prediction_timestamp": format_utc_timestamp(prediction_timestamp),
            "quote_observed_at": format_utc_timestamp(row["quote_observed_at"]),
            "as_of": format_utc_timestamp(row["as_of"]),
            "expiration": format_date_like(row["expiration"]),
            "spread_type": str(row["spread_type"]).strip(),
            "lower_strike": float(row["lower_strike"]),
            "upper_strike": float(row["upper_strike"]),
            "long_strike": float(row["long_strike"]),
            "short_strike": float(row["short_strike"]),
            "predicted_probability": float(row["probability_of_profit"]),
            "probability_model_name": str(row["probability_model_name"]).strip(),
            "probability_model_version": str(row["probability_model_version"]).strip(),
            "predicted_event_name": str(row["predicted_event_name"]).strip(),
            "predicted_event_direction": str(row["predicted_event_direction"]).strip(),
            "predicted_event_operator": str(row["predicted_event_operator"]).strip(),
            "predicted_event_threshold": float(row["predicted_event_threshold"]),
            "predicted_event_horizon": str(row["predicted_event_horizon"]).strip(),
            "required_outcome_horizon": str(row["predicted_event_horizon"]).strip(),
            "required_outcome_key": build_required_outcome_key(
                ticker=str(row["ticker"]),
                expiration=row["expiration"],
                required_outcome_horizon=str(row["predicted_event_horizon"]).strip(),
                realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
            ),
            "observation_group_id": observation_group_id,
        }
        for column in optional_columns:
            exported[column] = row.get(column)
        records.append(exported)

    exported_frame = pd.DataFrame.from_records(
        records,
        columns=list(PREDICTION_REQUIRED_COLUMNS) + optional_columns,
    )
    return validate_probability_prediction_frame(exported_frame)


def _compute_realized_event(row: pd.Series) -> int:
    """Compute one realized binary event using the exact predicted-event semantics."""
    if row["predicted_event_name"] != TERMINAL_BREAKEVEN_EVENT_NAME:
        raise ValueError(
            f"Unsupported predicted_event_name for calibration evaluation: {row['predicted_event_name']}"
        )
    if row["realized_outcome_measure"] != TERMINAL_UNDERLYING_OUTCOME_MEASURE:
        raise ValueError(
            "Unsupported realized_outcome_measure for calibration evaluation: "
            f"{row['realized_outcome_measure']}"
        )

    terminal_price = float(row["realized_terminal_underlying_price"])
    threshold = float(row["predicted_event_threshold"])
    direction = str(row["predicted_event_direction"]).strip()
    operator = str(row["predicted_event_operator"]).strip()

    if direction == "above" and operator == ">":
        return int(terminal_price > threshold)
    if direction == "below" and operator == "<":
        return int(terminal_price < threshold)
    raise ValueError(
        "predicted_event_direction and predicted_event_operator are unsupported or inconsistent."
    )


def join_predictions_with_realized_outcomes(
    predictions: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    allow_shared_outcome_keys: bool = False,
) -> pd.DataFrame:
    """Join validated predictions to realized outcomes and compute realized events."""
    validated_predictions = validate_probability_prediction_frame(predictions)
    validated_outcomes = validate_realized_outcome_frame(outcomes)

    outcome_key_counts = validated_predictions["required_outcome_key"].value_counts()
    if not allow_shared_outcome_keys and outcome_key_counts.gt(1).any():
        shared_keys = outcome_key_counts.loc[outcome_key_counts.gt(1)].index.tolist()
        joined_keys = ", ".join(shared_keys)
        raise ValueError(
            "Multiple predictions share the same required_outcome_key. "
            "Pass allow_shared_outcome_keys=True only when you intentionally want to evaluate "
            "correlated predictions against the same realized outcome. "
            f"shared_keys={joined_keys}"
        )

    merged = validated_predictions.merge(
        validated_outcomes,
        on="required_outcome_key",
        how="left",
        suffixes=("", "_outcome"),
        validate="many_to_one",
    )
    if merged["outcome_id"].isna().any():
        missing_prediction_ids = merged.loc[merged["outcome_id"].isna(), "prediction_id"].tolist()
        joined_ids = ", ".join(missing_prediction_ids)
        raise ValueError(
            "Missing realized outcomes for prediction_ids: "
            f"{joined_ids}"
        )

    if not merged["ticker"].eq(merged["ticker_outcome"]).all():
        raise ValueError("Prediction/outcome ticker mismatch detected during calibration join.")
    if not merged["expiration"].eq(merged["expiration_outcome"]).all():
        raise ValueError("Prediction/outcome expiration mismatch detected during calibration join.")
    if not merged["required_outcome_horizon"].eq(merged["required_outcome_horizon_outcome"]).all():
        raise ValueError(
            "Prediction/outcome horizon mismatch detected during calibration join."
        )
    if (merged["realized_outcome_observed_at"] <= merged["prediction_timestamp"]).any():
        raise ValueError(
            "realized_outcome_observed_at must be strictly later than prediction_timestamp."
        )
    if (merged["realized_outcome_observed_at"] <= merged["quote_observed_at"]).any():
        raise ValueError(
            "realized_outcome_observed_at must be strictly later than quote_observed_at."
        )

    merged["realized_event"] = merged.apply(_compute_realized_event, axis=1).astype(int)
    merged["outcome_key_prediction_count"] = merged["required_outcome_key"].map(outcome_key_counts).astype(int)
    merged["probability_error"] = merged["predicted_probability"] - merged["realized_event"]
    merged["absolute_error"] = merged["probability_error"].abs()
    merged["squared_error"] = merged["probability_error"] ** 2

    observation_frame = merged.rename(
        columns={
            "ticker_outcome": "ticker_realized",
            "expiration_outcome": "expiration_realized",
            "required_outcome_horizon_outcome": "required_outcome_horizon_realized",
        }
    )
    for optional_column in PREDICTION_OPTIONAL_COLUMNS:
        if optional_column not in observation_frame.columns:
            observation_frame[optional_column] = pd.NA

    for column in EVALUATION_OBSERVATION_COLUMNS:
        if column not in observation_frame.columns:
            observation_frame[column] = pd.NA

    return observation_frame.sort_values(
        by=["prediction_timestamp", "prediction_id"],
        kind="stable",
    )[list(EVALUATION_OBSERVATION_COLUMNS)].reset_index(drop=True)


def build_reliability_bins(
    observations: pd.DataFrame,
    *,
    bin_count: int = 10,
) -> pd.DataFrame:
    """Build fixed-width calibration bins on [0, 1], including empty bins."""
    if bin_count <= 0:
        raise ValueError("bin_count must be positive.")

    working = observations.copy()
    records: list[dict[str, Any]] = []
    for bin_index in range(bin_count):
        bin_lower = float(bin_index / bin_count)
        bin_upper = float((bin_index + 1) / bin_count)
        if bin_index == bin_count - 1:
            in_bin = working["predicted_probability"].between(bin_lower, bin_upper, inclusive="both")
            right_bracket = "]"
        else:
            in_bin = (
                working["predicted_probability"].ge(bin_lower)
                & working["predicted_probability"].lt(bin_upper)
            )
            right_bracket = ")"

        bin_rows = working.loc[in_bin].copy()
        prediction_count = int(len(bin_rows))
        if prediction_count == 0:
            mean_predicted_probability = float("nan")
            observed_event_rate = float("nan")
            event_count = 0
            calibration_gap = float("nan")
            absolute_calibration_gap = float("nan")
        else:
            mean_predicted_probability = float(bin_rows["predicted_probability"].mean())
            observed_event_rate = float(bin_rows["realized_event"].mean())
            event_count = int(bin_rows["realized_event"].sum())
            calibration_gap = float(mean_predicted_probability - observed_event_rate)
            absolute_calibration_gap = float(abs(calibration_gap))

        records.append(
            {
                "bin_index": bin_index,
                "bin_lower": bin_lower,
                "bin_upper": bin_upper,
                "bin_label": f"[{bin_lower:.1f}, {bin_upper:.1f}{right_bracket}",
                "prediction_count": prediction_count,
                "event_count": event_count,
                "mean_predicted_probability": mean_predicted_probability,
                "observed_event_rate": observed_event_rate,
                "calibration_gap": calibration_gap,
                "absolute_calibration_gap": absolute_calibration_gap,
            }
        )

    return pd.DataFrame(records, columns=list(RELIABILITY_BIN_COLUMNS))


def summarize_calibration(
    observations: pd.DataFrame,
    reliability_bins: pd.DataFrame,
    *,
    clip_epsilon: float = 1e-6,
) -> pd.DataFrame:
    """Compute one machine-readable calibration summary row."""
    if clip_epsilon <= 0 or clip_epsilon >= 0.5:
        raise ValueError("clip_epsilon must be between 0 and 0.5.")

    clipped = observations["predicted_probability"].clip(clip_epsilon, 1.0 - clip_epsilon)
    realized = observations["realized_event"].astype(float)
    log_loss = float(
        -((realized * clipped.map(math.log)) + ((1.0 - realized) * (1.0 - clipped).map(math.log))).mean()
    )
    non_empty_bins = reliability_bins.loc[reliability_bins["prediction_count"] > 0].copy()
    total_predictions = int(len(observations))
    if non_empty_bins.empty:
        expected_calibration_error = 0.0
        maximum_calibration_error = 0.0
    else:
        weights = non_empty_bins["prediction_count"] / total_predictions
        expected_calibration_error = float(
            (weights * non_empty_bins["absolute_calibration_gap"]).sum()
        )
        maximum_calibration_error = float(non_empty_bins["absolute_calibration_gap"].max())

    outcome_key_counts = observations["required_outcome_key"].value_counts()
    summary_row = {
        "prediction_count": total_predictions,
        "outcome_count": int(observations["required_outcome_key"].nunique()),
        "overall_event_rate": float(realized.mean()),
        "mean_predicted_probability": float(observations["predicted_probability"].mean()),
        "brier_score": float(observations["squared_error"].mean()),
        "log_loss": log_loss,
        "expected_calibration_error": expected_calibration_error,
        "maximum_calibration_error": maximum_calibration_error,
        "empty_bin_count": int((reliability_bins["prediction_count"] == 0).sum()),
        "non_empty_bin_count": int((reliability_bins["prediction_count"] > 0).sum()),
        "shared_outcome_key_count": int((outcome_key_counts > 1).sum()),
        "max_predictions_per_outcome_key": int(outcome_key_counts.max()),
    }
    return pd.DataFrame([summary_row], columns=list(CALIBRATION_SUMMARY_COLUMNS))


def build_reliability_summary(summary: pd.DataFrame) -> str:
    """Render one concise human-readable reliability summary."""
    if summary.empty:
        return "Calibration summary unavailable."

    row = summary.iloc[0]
    return (
        "Calibration summary: "
        f"n={int(row['prediction_count'])}, "
        f"event_rate={row['overall_event_rate']:.4f}, "
        f"mean_p={row['mean_predicted_probability']:.4f}, "
        f"brier={row['brier_score']:.6f}, "
        f"log_loss={row['log_loss']:.6f}, "
        f"ece={row['expected_calibration_error']:.6f}, "
        f"mce={row['maximum_calibration_error']:.6f}, "
        f"shared_outcome_keys={int(row['shared_outcome_key_count'])}"
    )


def evaluate_probability_predictions(
    predictions: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    bin_count: int = 10,
    clip_epsilon: float = 1e-6,
    allow_shared_outcome_keys: bool = False,
) -> CalibrationEvaluationArtifacts:
    """Validate, join, and score probability predictions against realized outcomes."""
    observations = join_predictions_with_realized_outcomes(
        predictions,
        outcomes,
        allow_shared_outcome_keys=allow_shared_outcome_keys,
    )
    reliability_bins = build_reliability_bins(observations, bin_count=bin_count)
    summary = summarize_calibration(
        observations,
        reliability_bins,
        clip_epsilon=clip_epsilon,
    )
    return CalibrationEvaluationArtifacts(
        observations=observations,
        reliability_bins=reliability_bins,
        summary=summary,
        reliability_summary=build_reliability_summary(summary),
    )
