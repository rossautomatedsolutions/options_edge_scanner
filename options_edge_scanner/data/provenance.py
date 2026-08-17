"""Helpers for local option-quote provenance and point-in-time validation."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


QUOTE_OBSERVED_AT_COLUMN = "quote_observed_at"
UNDERLYING_PRICE_OBSERVED_AT_COLUMN = "underlying_price_observed_at"
UNDERLYING_PRICE_SOURCE_COLUMN = "underlying_price_source"
SNAPSHOT_ID_COLUMN = "snapshot_id"
SNAPSHOT_SOURCE_COLUMN = "snapshot_source"
INPUT_PATH_COLUMN = "input_path"
SOURCE_METADATA_PATH_COLUMN = "source_metadata_path"

PROVENANCE_DATETIME_COLUMNS = (
    QUOTE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
)
PROVENANCE_STRING_COLUMNS = (
    SNAPSHOT_ID_COLUMN,
    SNAPSHOT_SOURCE_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
    INPUT_PATH_COLUMN,
    SOURCE_METADATA_PATH_COLUMN,
)
PROVENANCE_COLUMNS = PROVENANCE_DATETIME_COLUMNS + PROVENANCE_STRING_COLUMNS
NULL_LIKE_STRING_VALUES = frozenset({"", "nan", "<na>", "none", "null", "nat"})


def _normalize_timestamp_scalar(value: Any) -> pd.Timestamp | pd.NaT:
    """Return one timezone-naive timestamp or NaT."""
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return pd.NaT
    return pd.Timestamp(timestamp).tz_localize(None)


def _normalize_timestamp_series(series: pd.Series) -> pd.Series:
    """Parse one timestamp-like series into timezone-naive pandas timestamps."""
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.tz_localize(None)


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
    """Return one trimmed nullable string series with null-like tokens cleared."""
    normalized = series.astype("string").str.strip()
    null_like = normalized.str.casefold().fillna("").isin(NULL_LIKE_STRING_VALUES)
    return normalized.mask(null_like, pd.NA)


def _metadata_requires_snapshot_id(
    *,
    input_path: str | Path | None,
    metadata_file: Path | None,
    metadata_payload: dict[str, Any],
) -> bool:
    """Return whether the current sidecar is expected to carry snapshot_id."""
    source_vendor = _normalize_string_scalar(metadata_payload.get("source_vendor"))
    source_library = _normalize_string_scalar(metadata_payload.get("source_library"))
    snapshot_source = _normalize_string_scalar(metadata_payload.get(SNAPSHOT_SOURCE_COLUMN))
    if source_vendor == "yahoo_finance" or source_library == "yfinance" or snapshot_source == "yahoo_finance":
        return True

    candidate_names: list[str] = []
    if input_path is not None:
        candidate_names.append(Path(input_path).name)
    if metadata_file is not None:
        candidate_names.append(metadata_file.name.removesuffix(".meta.json"))
    return any(name.casefold().endswith("_yahoo.csv") for name in candidate_names)


def _is_day_precision_as_of(value: Any) -> bool:
    """Return whether one as-of input should be interpreted as a day-level bound."""
    if isinstance(value, str):
        return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()) is not None
    if isinstance(value, date) and not isinstance(value, datetime):
        return True
    return False


def normalize_provenance_columns(option_quotes: pd.DataFrame) -> pd.DataFrame:
    """Normalize known provenance columns when they are present."""
    working = option_quotes.copy()
    for column in PROVENANCE_DATETIME_COLUMNS:
        if column in working.columns:
            working[column] = _normalize_timestamp_series(working[column])
    for column in PROVENANCE_STRING_COLUMNS:
        if column in working.columns:
            working[column] = _normalize_string_series(working[column])
    return working


def _infer_metadata_sidecar_path(input_path: str | Path) -> Path | None:
    """Return the sibling metadata sidecar path when it exists."""
    file_path = Path(input_path)
    candidate = file_path.with_suffix(file_path.suffix + ".meta.json")
    if candidate.exists():
        return candidate
    return None


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Read a JSON metadata sidecar, returning an empty dict on parse failure."""
    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fill_string_column(
    option_quotes: pd.DataFrame,
    *,
    column: str,
    value: Any,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Populate one provenance string column while preserving existing non-empty values."""
    normalized = _normalize_string_scalar(value)
    if normalized is None:
        return option_quotes

    working = option_quotes.copy()
    if column not in working.columns or overwrite:
        working[column] = normalized
        return working

    existing = _normalize_string_series(working[column])
    working[column] = existing.where(existing.notna(), normalized)
    return working


def enrich_option_quote_provenance(
    option_quotes: pd.DataFrame,
    *,
    input_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
    input_path_ref: str | None = None,
    metadata_path_ref: str | None = None,
    snapshot_id: str | None = None,
    snapshot_source: str | None = None,
) -> pd.DataFrame:
    """Fill repo-supported provenance fields from local file context when possible."""
    working = normalize_provenance_columns(option_quotes)

    metadata_file: Path | None = Path(metadata_path) if metadata_path is not None else None
    if input_path is not None:
        input_value = input_path_ref if input_path_ref is not None else str(Path(input_path))
        working[INPUT_PATH_COLUMN] = str(input_value).strip()
        if metadata_file is None:
            metadata_file = _infer_metadata_sidecar_path(input_path)
        if metadata_file is not None:
            metadata_value = (
                metadata_path_ref
                if metadata_path_ref is not None
                else str(metadata_file)
            )
            working[SOURCE_METADATA_PATH_COLUMN] = str(metadata_value).strip()
    elif input_path_ref is not None:
        working[INPUT_PATH_COLUMN] = str(input_path_ref).strip()

    if metadata_file is not None and SOURCE_METADATA_PATH_COLUMN not in working.columns:
        metadata_value = metadata_path_ref if metadata_path_ref is not None else str(metadata_file)
        working[SOURCE_METADATA_PATH_COLUMN] = str(metadata_value).strip()
    elif metadata_path_ref is not None and SOURCE_METADATA_PATH_COLUMN not in working.columns:
        working[SOURCE_METADATA_PATH_COLUMN] = str(metadata_path_ref).strip()

    metadata_payload: dict[str, Any] = {}
    if metadata_file is None and SOURCE_METADATA_PATH_COLUMN in working.columns:
        first_metadata_path = next(
            (
                Path(value)
                for value in working[SOURCE_METADATA_PATH_COLUMN].dropna().astype(str).tolist()
                if value
            ),
            None,
        )
        if first_metadata_path is not None and first_metadata_path.exists():
            metadata_file = first_metadata_path
    if metadata_file is not None and metadata_file.exists():
        metadata_payload = _read_metadata_payload(metadata_file)
    metadata_snapshot_id = _normalize_string_scalar(metadata_payload.get(SNAPSHOT_ID_COLUMN))
    if _metadata_requires_snapshot_id(
        input_path=input_path,
        metadata_file=metadata_file,
        metadata_payload=metadata_payload,
    ) and metadata_snapshot_id is None:
        raise ValueError("Yahoo option-chain metadata sidecar must include a non-empty snapshot_id.")

    fill_values = {
        QUOTE_OBSERVED_AT_COLUMN: metadata_payload.get(
            QUOTE_OBSERVED_AT_COLUMN,
            metadata_payload.get("fetched_at_utc"),
        ),
        UNDERLYING_PRICE_OBSERVED_AT_COLUMN: metadata_payload.get(
            UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
            metadata_payload.get("fetched_at_utc"),
        ),
        UNDERLYING_PRICE_SOURCE_COLUMN: metadata_payload.get(UNDERLYING_PRICE_SOURCE_COLUMN),
        SNAPSHOT_ID_COLUMN: metadata_payload.get(SNAPSHOT_ID_COLUMN),
        SNAPSHOT_SOURCE_COLUMN: metadata_payload.get(
            SNAPSHOT_SOURCE_COLUMN,
            metadata_payload.get("source_vendor", metadata_payload.get("source")),
        ),
    }

    for column in PROVENANCE_DATETIME_COLUMNS:
        value = fill_values.get(column)
        if value is None:
            continue
        if column not in working.columns:
            working[column] = _normalize_timestamp_scalar(value)
            continue
        normalized_value = _normalize_timestamp_scalar(value)
        working[column] = working[column].where(working[column].notna(), normalized_value)

    string_value = fill_values.get(UNDERLYING_PRICE_SOURCE_COLUMN)
    working = _fill_string_column(
        working,
        column=UNDERLYING_PRICE_SOURCE_COLUMN,
        value=string_value,
    )
    working = _fill_string_column(
        working,
        column=SNAPSHOT_ID_COLUMN,
        value=fill_values.get(SNAPSHOT_ID_COLUMN),
    )
    working = _fill_string_column(
        working,
        column=SNAPSHOT_ID_COLUMN,
        value=snapshot_id,
        overwrite=snapshot_id is not None,
    )
    working = _fill_string_column(
        working,
        column=SNAPSHOT_SOURCE_COLUMN,
        value=fill_values.get(SNAPSHOT_SOURCE_COLUMN),
    )
    working = _fill_string_column(
        working,
        column=SNAPSHOT_SOURCE_COLUMN,
        value=snapshot_source,
        overwrite=snapshot_source is not None,
    )

    return normalize_provenance_columns(working)


def resolve_effective_as_of(
    option_quotes: pd.DataFrame,
    *,
    explicit_as_of: Any | None,
) -> tuple[pd.Timestamp, bool]:
    """Resolve the effective as-of timestamp and whether it is day precision."""
    if explicit_as_of is not None:
        return _normalize_timestamp_scalar(explicit_as_of), _is_day_precision_as_of(explicit_as_of)

    if QUOTE_OBSERVED_AT_COLUMN in option_quotes.columns:
        observed = _normalize_timestamp_series(option_quotes[QUOTE_OBSERVED_AT_COLUMN]).dropna()
        if not observed.empty:
            return observed.max(), False

    return pd.Timestamp.utcnow().tz_localize(None).normalize(), True


def validate_point_in_time_integrity(
    option_quotes: pd.DataFrame,
    *,
    as_of: Any,
    as_of_day_precision: bool = False,
    allow_unsafe_as_of: bool = False,
) -> pd.DataFrame:
    """Reject historical-style scans that lack or misuse observation provenance."""
    working = normalize_provenance_columns(option_quotes)
    if allow_unsafe_as_of:
        return working

    as_of_ts = _normalize_timestamp_scalar(as_of)
    if QUOTE_OBSERVED_AT_COLUMN not in working.columns:
        raise ValueError(
            "Point-in-time scans require quote_observed_at provenance. "
            "Add quote_observed_at or a sibling .meta.json sidecar, or pass --allow-unsafe-as-of."
        )

    observed_quotes = _normalize_timestamp_series(working[QUOTE_OBSERVED_AT_COLUMN]).dropna()
    if observed_quotes.empty:
        raise ValueError(
            "Point-in-time scans require non-empty quote_observed_at provenance. "
            "Populate quote_observed_at or pass --allow-unsafe-as-of."
        )

    latest_quote_observed_at = observed_quotes.max()
    quote_lookahead = (
        latest_quote_observed_at.normalize() > as_of_ts.normalize()
        if as_of_day_precision
        else latest_quote_observed_at > as_of_ts
    )
    if quote_lookahead:
        raise ValueError(
            f"as_of {as_of_ts} predates the observed option snapshot timestamp "
            f"{latest_quote_observed_at}. Pass --allow-unsafe-as-of to override."
        )

    if UNDERLYING_PRICE_OBSERVED_AT_COLUMN in working.columns:
        observed_spot = _normalize_timestamp_series(
            working[UNDERLYING_PRICE_OBSERVED_AT_COLUMN]
        ).dropna()
        if not observed_spot.empty:
            latest_spot_observed_at = observed_spot.max()
            spot_lookahead = (
                latest_spot_observed_at.normalize() > as_of_ts.normalize()
                if as_of_day_precision
                else latest_spot_observed_at > as_of_ts
            )
            if spot_lookahead:
                raise ValueError(
                    f"as_of {as_of_ts} predates the observed underlying-price timestamp "
                    f"{latest_spot_observed_at}. Pass --allow-unsafe-as-of to override."
                )

    return working
