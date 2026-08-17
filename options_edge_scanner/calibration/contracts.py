"""Explicit prediction/outcome contracts for probability calibration workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


TERMINAL_UNDERLYING_OUTCOME_MEASURE = "terminal_underlying_price"

PREDICTION_REQUIRED_COLUMNS = (
    "prediction_id",
    "snapshot_id",
    "ticker",
    "prediction_timestamp",
    "quote_observed_at",
    "as_of",
    "expiration",
    "spread_type",
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "predicted_probability",
    "probability_model_name",
    "probability_model_version",
    "predicted_event_name",
    "predicted_event_direction",
    "predicted_event_operator",
    "predicted_event_threshold",
    "predicted_event_horizon",
    "required_outcome_horizon",
    "required_outcome_key",
    "observation_group_id",
)
PREDICTION_OPTIONAL_COLUMNS = (
    "snapshot_source",
    "input_path",
    "source_metadata_path",
)

OUTCOME_REQUIRED_COLUMNS = (
    "outcome_id",
    "required_outcome_key",
    "ticker",
    "expiration",
    "required_outcome_horizon",
    "realized_outcome_measure",
    "realized_terminal_underlying_price",
    "realized_outcome_observed_at",
    "realized_outcome_source",
)

EVALUATION_OBSERVATION_COLUMNS = (
    "prediction_id",
    "outcome_id",
    "snapshot_id",
    "snapshot_source",
    "ticker",
    "prediction_timestamp",
    "quote_observed_at",
    "as_of",
    "expiration",
    "spread_type",
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "predicted_probability",
    "probability_model_name",
    "probability_model_version",
    "predicted_event_name",
    "predicted_event_direction",
    "predicted_event_operator",
    "predicted_event_threshold",
    "predicted_event_horizon",
    "required_outcome_horizon",
    "required_outcome_key",
    "observation_group_id",
    "input_path",
    "source_metadata_path",
    "realized_outcome_measure",
    "realized_terminal_underlying_price",
    "realized_outcome_observed_at",
    "realized_outcome_source",
    "realized_event",
    "outcome_key_prediction_count",
    "probability_error",
    "absolute_error",
    "squared_error",
)

RELIABILITY_BIN_COLUMNS = (
    "bin_index",
    "bin_lower",
    "bin_upper",
    "bin_label",
    "prediction_count",
    "event_count",
    "mean_predicted_probability",
    "observed_event_rate",
    "calibration_gap",
    "absolute_calibration_gap",
)

CALIBRATION_SUMMARY_COLUMNS = (
    "prediction_count",
    "outcome_count",
    "overall_event_rate",
    "mean_predicted_probability",
    "brier_score",
    "log_loss",
    "expected_calibration_error",
    "maximum_calibration_error",
    "empty_bin_count",
    "non_empty_bin_count",
    "shared_outcome_key_count",
    "max_predictions_per_outcome_key",
)

_FULL_TIMESTAMP_WITH_TIMEZONE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
NULL_LIKE_STRING_VALUES = frozenset({"", "nan", "<na>", "none", "null", "nat"})


def _normalize_string_scalar(value: Any) -> str | None:
    """Return one trimmed scalar string or None when it is null-like."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.casefold() in NULL_LIKE_STRING_VALUES:
        return None
    return normalized


def _normalize_string_series(series: pd.Series) -> pd.Series:
    """Return one trimmed nullable string series."""
    normalized = series.astype("string").str.strip()
    null_like = normalized.str.casefold().fillna("").isin(NULL_LIKE_STRING_VALUES)
    return normalized.mask(null_like, pd.NA)


def _require_non_empty_strings(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Require non-empty string values for the requested columns."""
    working = frame.copy()
    for column in columns:
        working[column] = _normalize_string_series(working[column])
        if working[column].isna().any():
            raise ValueError(f"{column} must be present and non-empty.")
    return working


def _require_full_timestamp_strings(series: pd.Series, *, column: str) -> None:
    """Reject timestamp strings that omit explicit time or timezone information."""
    for value in series.dropna().tolist():
        if isinstance(value, pd.Timestamp):
            continue
        if hasattr(value, "isoformat") and not isinstance(value, str):
            continue

        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{column} must not be blank.")
        if _FULL_TIMESTAMP_WITH_TIMEZONE_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                f"{column} must use full ISO-8601 timestamps with explicit timezone, "
                f"such as 2026-01-02T15:30:00Z. Received: {value}"
            )


def _parse_timestamp_series(series: pd.Series, *, column: str) -> pd.Series:
    """Parse one full-timestamp series into timezone-naive UTC timestamps."""
    _require_full_timestamp_strings(series, column=column)
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError(f"{column} must contain valid timestamps.")
    return parsed.dt.tz_localize(None)


def _parse_date_series(series: pd.Series, *, column: str) -> pd.Series:
    """Parse one date-like series into normalized timestamps."""
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError(f"{column} must contain valid date-like values.")
    return parsed.dt.tz_localize(None).dt.normalize()


def _parse_numeric_series(series: pd.Series, *, column: str) -> pd.Series:
    """Parse one numeric series and reject missing/invalid values."""
    parsed = pd.to_numeric(series, errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{column} must contain numeric values.")
    return parsed.astype(float)


def format_utc_timestamp(value: Any) -> str:
    """Format one timestamp-like value as an explicit UTC ISO string."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"Timestamp value is invalid: {value}")
    timestamp = pd.Timestamp(parsed)
    base = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    if timestamp.microsecond:
        return timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return base + "Z"


def format_date_like(value: Any) -> str:
    """Format one date-like value as YYYY-MM-DD."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"Date-like value is invalid: {value}")
    return pd.Timestamp(parsed).strftime("%Y-%m-%d")


def build_required_outcome_key(
    *,
    ticker: str,
    expiration: Any,
    required_outcome_horizon: str,
    realized_outcome_measure: str = TERMINAL_UNDERLYING_OUTCOME_MEASURE,
) -> str:
    """Build one stable future-outcome join key."""
    return "|".join(
        [
            str(ticker).strip().upper(),
            format_date_like(expiration),
            str(required_outcome_horizon).strip(),
            str(realized_outcome_measure).strip(),
        ]
    )


def build_observation_group_id(
    *,
    snapshot_id: str,
    ticker: str,
    prediction_timestamp: Any,
    expiration: Any,
) -> str:
    """Build one correlation-group identifier for related predictions."""
    normalized_snapshot_id = _normalize_string_scalar(snapshot_id)
    if normalized_snapshot_id is None:
        raise ValueError("snapshot_id must be present and non-empty.")
    return "|".join(
        [
            normalized_snapshot_id,
            str(ticker).strip().upper(),
            format_utc_timestamp(prediction_timestamp),
            format_date_like(expiration),
        ]
    )


def build_prediction_id(
    *,
    observation_group_id: str,
    spread_type: str,
    lower_strike: Any,
    upper_strike: Any,
    probability_model_name: str,
    probability_model_version: str,
) -> str:
    """Build one stable prediction identifier for exported scanner rows."""
    return "|".join(
        [
            str(observation_group_id).strip(),
            str(spread_type).strip(),
            f"{float(lower_strike):.6f}",
            f"{float(upper_strike):.6f}",
            str(probability_model_name).strip(),
            str(probability_model_version).strip(),
        ]
    )


def _validate_prediction_semantic_uniqueness(frame: pd.DataFrame) -> None:
    """Reject exact duplicate prediction semantics with different identifiers."""
    semantic_columns = [
        "snapshot_id",
        "ticker",
        "prediction_timestamp",
        "expiration",
        "spread_type",
        "lower_strike",
        "upper_strike",
        "predicted_event_name",
        "predicted_event_direction",
        "predicted_event_operator",
        "predicted_event_threshold",
        "probability_model_name",
        "probability_model_version",
    ]
    duplicated = frame.duplicated(subset=semantic_columns, keep=False)
    if duplicated.any():
        duplicate_ids = frame.loc[duplicated, "prediction_id"].tolist()
        joined_ids = ", ".join(duplicate_ids)
        raise ValueError(
            "Duplicate semantic predictions are not allowed without explicit treatment. "
            f"prediction_ids={joined_ids}"
        )


def _validate_prediction_contract_keys(frame: pd.DataFrame) -> None:
    """Reject prediction-side linkage fields that disagree with row semantics."""
    expected_outcome_keys = pd.Series(
        [
            build_required_outcome_key(
                ticker=row["ticker"],
                expiration=row["expiration"],
                required_outcome_horizon=row["required_outcome_horizon"],
            )
            for row in frame.to_dict("records")
        ],
        index=frame.index,
        dtype="string",
    )
    if not frame["required_outcome_key"].eq(expected_outcome_keys).all():
        raise ValueError("required_outcome_key does not match prediction contract fields.")

    expected_observation_group_ids = pd.Series(
        [
            build_observation_group_id(
                snapshot_id=row["snapshot_id"],
                ticker=row["ticker"],
                prediction_timestamp=row["prediction_timestamp"],
                expiration=row["expiration"],
            )
            for row in frame.to_dict("records")
        ],
        index=frame.index,
        dtype="string",
    )
    if not frame["observation_group_id"].eq(expected_observation_group_ids).all():
        raise ValueError("observation_group_id does not match prediction contract fields.")


def _validate_outcome_contract_keys(frame: pd.DataFrame) -> None:
    """Reject realized-outcome linkage fields that disagree with row semantics."""
    expected_outcome_keys = pd.Series(
        [
            build_required_outcome_key(
                ticker=row["ticker"],
                expiration=row["expiration"],
                required_outcome_horizon=row["required_outcome_horizon"],
                realized_outcome_measure=row["realized_outcome_measure"],
            )
            for row in frame.to_dict("records")
        ],
        index=frame.index,
        dtype="string",
    )
    if not frame["required_outcome_key"].eq(expected_outcome_keys).all():
        raise ValueError("required_outcome_key does not match realized outcome contract fields.")


def validate_probability_prediction_frame(predictions: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize one probability-prediction frame."""
    missing_columns = [column for column in PREDICTION_REQUIRED_COLUMNS if column not in predictions.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required ProbabilityPredictionRow columns: {missing}")

    working = predictions.copy()
    working = _require_non_empty_strings(
        working,
        columns=(
            "prediction_id",
            "snapshot_id",
            "ticker",
            "spread_type",
            "probability_model_name",
            "probability_model_version",
            "predicted_event_name",
            "predicted_event_direction",
            "predicted_event_operator",
            "predicted_event_horizon",
            "required_outcome_horizon",
            "required_outcome_key",
            "observation_group_id",
        ),
    )
    working["ticker"] = working["ticker"].str.upper()
    working["prediction_timestamp"] = _parse_timestamp_series(
        working["prediction_timestamp"],
        column="prediction_timestamp",
    )
    working["quote_observed_at"] = _parse_timestamp_series(
        working["quote_observed_at"],
        column="quote_observed_at",
    )
    working["as_of"] = _parse_timestamp_series(working["as_of"], column="as_of")
    working["expiration"] = _parse_date_series(working["expiration"], column="expiration")

    for column in ("lower_strike", "upper_strike", "long_strike", "short_strike", "predicted_event_threshold"):
        working[column] = _parse_numeric_series(working[column], column=column)
    working["predicted_probability"] = _parse_numeric_series(
        working["predicted_probability"],
        column="predicted_probability",
    )

    if working["predicted_probability"].lt(0.0).any() or working["predicted_probability"].gt(1.0).any():
        raise ValueError("predicted_probability must be within [0, 1].")
    if working["prediction_id"].duplicated().any():
        raise ValueError("prediction_id values must be unique.")
    if (working["prediction_timestamp"] < working["quote_observed_at"]).any():
        raise ValueError("prediction_timestamp must be on or after quote_observed_at.")
    if (working["prediction_timestamp"] < working["as_of"]).any():
        raise ValueError("prediction_timestamp must be on or after as_of.")
    if (working["prediction_timestamp"].dt.normalize() > working["expiration"]).any():
        raise ValueError("prediction_timestamp must not postdate expiration.")
    expiration_horizon_rows = working["predicted_event_horizon"].eq("expiration")
    if (
        expiration_horizon_rows
        & working["prediction_timestamp"].dt.normalize().ge(working["expiration"])
    ).any():
        raise ValueError(
            "expiration-horizon predictions must be observed before the expiration date."
        )
    if not working["predicted_event_direction"].isin(["above", "below"]).all():
        raise ValueError("predicted_event_direction must be one of: above, below.")
    if not working["predicted_event_operator"].isin([">", "<"]).all():
        raise ValueError("predicted_event_operator must be one of: >, <.")
    if not working["required_outcome_horizon"].eq(working["predicted_event_horizon"]).all():
        raise ValueError("required_outcome_horizon must match predicted_event_horizon.")

    direction_operator_mismatch = (
        ((working["predicted_event_direction"] == "above") & (working["predicted_event_operator"] != ">"))
        | ((working["predicted_event_direction"] == "below") & (working["predicted_event_operator"] != "<"))
    )
    if direction_operator_mismatch.any():
        raise ValueError("predicted_event_direction and predicted_event_operator disagree.")

    _validate_prediction_contract_keys(working)
    _validate_prediction_semantic_uniqueness(working)
    return working.sort_values(
        by=["prediction_timestamp", "prediction_id"],
        kind="stable",
    ).reset_index(drop=True)


def validate_realized_outcome_frame(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize one realized-outcome frame."""
    missing_columns = [column for column in OUTCOME_REQUIRED_COLUMNS if column not in outcomes.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required RealizedOutcomeRow columns: {missing}")

    working = outcomes.copy()
    working = _require_non_empty_strings(
        working,
        columns=(
            "outcome_id",
            "required_outcome_key",
            "ticker",
            "required_outcome_horizon",
            "realized_outcome_measure",
            "realized_outcome_source",
        ),
    )
    working["ticker"] = working["ticker"].str.upper()
    working["expiration"] = _parse_date_series(working["expiration"], column="expiration")
    working["realized_outcome_observed_at"] = _parse_timestamp_series(
        working["realized_outcome_observed_at"],
        column="realized_outcome_observed_at",
    )
    working["realized_terminal_underlying_price"] = _parse_numeric_series(
        working["realized_terminal_underlying_price"],
        column="realized_terminal_underlying_price",
    )

    if working["outcome_id"].duplicated().any():
        raise ValueError("outcome_id values must be unique.")
    if working["required_outcome_key"].duplicated().any():
        raise ValueError("required_outcome_key values must be unique in realized outcomes.")
    if not working["realized_outcome_measure"].eq(TERMINAL_UNDERLYING_OUTCOME_MEASURE).all():
        raise ValueError(
            f"realized_outcome_measure must equal {TERMINAL_UNDERLYING_OUTCOME_MEASURE}."
        )
    if (working["realized_outcome_observed_at"].dt.normalize() < working["expiration"]).any():
        raise ValueError("realized_outcome_observed_at must be on or after expiration.")

    _validate_outcome_contract_keys(working)
    return working.sort_values(
        by=["realized_outcome_observed_at", "outcome_id"],
        kind="stable",
    ).reset_index(drop=True)


def ensure_parent(path: str | Path) -> Path:
    """Create the parent directory for one output artifact path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path
