"""Provider-neutral realized underlying observation contracts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from options_edge_scanner.calibration.contracts import (
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    build_required_outcome_key,
    ensure_parent,
    format_date_like,
    format_utc_timestamp,
)
from options_edge_scanner.calibration.terminal_semantics import (
    TerminalObservationPolicy,
    market_close_timestamp_for_event_date,
    resolve_terminal_observation_policy,
)


REALIZED_UNDERLYING_REQUIRED_COLUMNS = (
    "observation_id",
    "required_outcome_key",
    "ticker",
    "event_date",
    "required_outcome_horizon",
    "realized_outcome_measure",
    "terminal_price_convention",
    "terminal_price_convention_version",
    "observed_price",
    "observed_at",
    "market_close_timestamp",
    "price_field",
    "observed_market_session",
    "source",
    "source_dataset",
    "source_feed",
    "timeframe",
    "adjustment_mode",
    "acquired_at",
    "provenance_artifact_id",
)
REALIZED_UNDERLYING_OPTIONAL_COLUMNS = (
    "source_bar_timestamp",
    "provider_symbol",
    "currency",
)

_FULL_TIMESTAMP_WITH_TIMEZONE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


def _normalize_string_series(series: pd.Series) -> pd.Series:
    """Return one trimmed nullable string series."""
    return series.astype("string").str.strip()


def _require_non_empty_strings(frame: pd.DataFrame, *, columns: Iterable[str]) -> pd.DataFrame:
    """Require non-empty string values for the requested columns."""
    working = frame.copy()
    for column in columns:
        working[column] = _normalize_string_series(working[column])
        if working[column].isna().any() or working[column].eq("").any():
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
                f"such as 2026-01-02T20:00:00Z. Received: {value}"
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
    """Parse one numeric series and reject missing or invalid values."""
    parsed = pd.to_numeric(series, errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{column} must contain numeric values.")
    return parsed.astype(float)


def build_realized_underlying_artifact_id(
    *,
    source: str,
    ticker: str,
    start: object,
    end: object,
    timeframe: str,
    adjustment_mode: str,
    source_feed: str,
    terminal_price_convention: str,
) -> str:
    """Build one stable realized underlying artifact identifier."""
    return "|".join(
        [
            str(source).strip(),
            str(ticker).strip().upper(),
            format_date_like(start),
            format_date_like(end),
            str(timeframe).strip(),
            str(adjustment_mode).strip(),
            str(source_feed).strip(),
            str(terminal_price_convention).strip(),
        ]
    )


def build_realized_underlying_observation_id(
    *,
    ticker: str,
    event_date: object,
    required_outcome_horizon: str,
    realized_outcome_measure: str,
    terminal_price_convention: str,
    terminal_price_convention_version: str,
    source: str,
    source_dataset: str,
    source_feed: str,
    timeframe: str,
    adjustment_mode: str,
) -> str:
    """Build one stable realized underlying observation identifier."""
    return "|".join(
        [
            str(ticker).strip().upper(),
            format_date_like(event_date),
            str(required_outcome_horizon).strip(),
            str(realized_outcome_measure).strip(),
            str(terminal_price_convention).strip(),
            str(terminal_price_convention_version).strip(),
            str(source).strip(),
            str(source_dataset).strip(),
            str(source_feed).strip(),
            str(timeframe).strip(),
            str(adjustment_mode).strip(),
        ]
    )


def _validate_policy_rows(frame: pd.DataFrame) -> None:
    """Validate row semantics against the explicit terminal observation policy."""
    for row in frame.to_dict("records"):
        policy: TerminalObservationPolicy = resolve_terminal_observation_policy(
            ticker=row["ticker"],
            required_outcome_horizon=row["required_outcome_horizon"],
        )
        if row["realized_outcome_measure"] != TERMINAL_UNDERLYING_OUTCOME_MEASURE:
            raise ValueError(
                "realized_outcome_measure must equal terminal_underlying_price for realized "
                "underlying observations."
            )
        if row["terminal_price_convention"] != policy.terminal_price_convention:
            raise ValueError(
                "terminal_price_convention does not match the explicit policy for "
                f"{row['ticker']}."
            )
        if row["terminal_price_convention_version"] != policy.terminal_price_convention_version:
            raise ValueError(
                "terminal_price_convention_version does not match the explicit policy for "
                f"{row['ticker']}."
            )
        if row["price_field"] != policy.price_field:
            raise ValueError(f"price_field must equal {policy.price_field}.")
        if row["observed_market_session"] != policy.observed_market_session:
            raise ValueError(
                f"observed_market_session must equal {policy.observed_market_session}."
            )

        expected_outcome_key = build_required_outcome_key(
            ticker=row["ticker"],
            expiration=row["event_date"],
            required_outcome_horizon=row["required_outcome_horizon"],
            realized_outcome_measure=row["realized_outcome_measure"],
        )
        if row["required_outcome_key"] != expected_outcome_key:
            raise ValueError(
                "required_outcome_key does not match realized underlying contract fields."
            )

        expected_market_close = market_close_timestamp_for_event_date(
            row["event_date"],
            policy=policy,
        )
        if format_utc_timestamp(row["market_close_timestamp"]) != expected_market_close:
            raise ValueError(
                "market_close_timestamp does not match the explicit terminal observation policy."
            )

        expected_observation_id = build_realized_underlying_observation_id(
            ticker=row["ticker"],
            event_date=row["event_date"],
            required_outcome_horizon=row["required_outcome_horizon"],
            realized_outcome_measure=row["realized_outcome_measure"],
            terminal_price_convention=row["terminal_price_convention"],
            terminal_price_convention_version=row["terminal_price_convention_version"],
            source=row["source"],
            source_dataset=row["source_dataset"],
            source_feed=row["source_feed"],
            timeframe=row["timeframe"],
            adjustment_mode=row["adjustment_mode"],
        )
        if row["observation_id"] != expected_observation_id:
            raise ValueError("observation_id does not match realized underlying contract fields.")


def validate_realized_underlying_frame(observations: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize one provider-neutral realized underlying frame."""
    missing_columns = [
        column for column in REALIZED_UNDERLYING_REQUIRED_COLUMNS if column not in observations.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required RealizedUnderlyingObservationRow columns: {missing}")

    working = observations.copy()
    working = _require_non_empty_strings(
        working,
        columns=(
            "observation_id",
            "required_outcome_key",
            "ticker",
            "required_outcome_horizon",
            "realized_outcome_measure",
            "terminal_price_convention",
            "terminal_price_convention_version",
            "price_field",
            "observed_market_session",
            "source",
            "source_dataset",
            "source_feed",
            "timeframe",
            "adjustment_mode",
            "provenance_artifact_id",
        ),
    )
    working["ticker"] = working["ticker"].str.upper()
    working["event_date"] = _parse_date_series(working["event_date"], column="event_date")
    working["observed_at"] = _parse_timestamp_series(working["observed_at"], column="observed_at")
    working["market_close_timestamp"] = _parse_timestamp_series(
        working["market_close_timestamp"],
        column="market_close_timestamp",
    )
    working["acquired_at"] = _parse_timestamp_series(working["acquired_at"], column="acquired_at")
    working["observed_price"] = _parse_numeric_series(working["observed_price"], column="observed_price")

    for column in REALIZED_UNDERLYING_OPTIONAL_COLUMNS:
        if column in working.columns:
            if column == "source_bar_timestamp":
                normalized = _normalize_string_series(working[column])
                present = normalized.dropna()
                present = present.loc[present.ne("")]
                if not present.empty:
                    _require_full_timestamp_strings(present, column=column)
                working[column] = normalized.where(normalized.ne(""), pd.NA)
            else:
                working[column] = _normalize_string_series(working[column])

    if working["observation_id"].duplicated().any():
        raise ValueError("observation_id values must be unique.")
    if working["required_outcome_key"].duplicated().any():
        raise ValueError(
            "required_outcome_key values must be unique in realized underlying observations."
        )
    if (working["observed_at"] != working["market_close_timestamp"]).any():
        raise ValueError(
            "observed_at must equal market_close_timestamp for the current explicit terminal "
            "observation policy."
        )
    if (working["market_close_timestamp"].dt.normalize() != working["event_date"]).any():
        raise ValueError("market_close_timestamp must fall on event_date.")
    if (working["observed_at"].dt.normalize() != working["event_date"]).any():
        raise ValueError("observed_at must fall on event_date.")
    if (working["acquired_at"] < working["observed_at"]).any():
        raise ValueError("acquired_at must be on or after observed_at.")

    _validate_policy_rows(working)
    return working.sort_values(
        by=["event_date", "observed_at", "observation_id"],
        kind="stable",
    ).reset_index(drop=True)


def load_realized_underlying_frame(path: str | Path) -> pd.DataFrame:
    """Load and validate one realized underlying artifact CSV."""
    return validate_realized_underlying_frame(pd.read_csv(path))


def load_realized_underlying_artifacts(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Load and concatenate one or more realized underlying artifact CSVs strictly."""
    frames = [load_realized_underlying_frame(path) for path in paths]
    if not frames:
        return pd.DataFrame(columns=list(REALIZED_UNDERLYING_REQUIRED_COLUMNS))
    return validate_realized_underlying_frame(pd.concat(frames, ignore_index=True))


def write_realized_underlying_frame(
    observations: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Validate and write one realized underlying artifact CSV."""
    validated = validate_realized_underlying_frame(observations)
    serialized = validated.copy()
    serialized["event_date"] = serialized["event_date"].map(format_date_like)
    serialized["observed_at"] = serialized["observed_at"].map(format_utc_timestamp)
    serialized["market_close_timestamp"] = serialized["market_close_timestamp"].map(format_utc_timestamp)
    serialized["acquired_at"] = serialized["acquired_at"].map(format_utc_timestamp)
    if "source_bar_timestamp" in serialized.columns:
        serialized["source_bar_timestamp"] = serialized["source_bar_timestamp"].astype("string")
    path = ensure_parent(output_path)
    serialized.to_csv(path, index=False)
    return path
