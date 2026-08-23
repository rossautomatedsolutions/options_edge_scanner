"""Strict manifest/loader support for historically safe local snapshot scans."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

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


HISTORICAL_SNAPSHOT_MANIFEST_REQUIRED_COLUMNS = (
    SNAPSHOT_ID_COLUMN,
    "ticker",
    "as_of",
    "chain_path",
    "metadata_path",
)
HISTORICAL_SNAPSHOT_MANIFEST_OPTIONAL_COLUMNS = (
    SNAPSHOT_SOURCE_COLUMN,
    QUOTE_OBSERVED_AT_COLUMN,
    "underlying_price",
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
    "expiration_start",
    "expiration_end",
)


@dataclass(frozen=True)
class HistoricalSnapshotSpec:
    """Validated manifest row with resolved local artifact paths."""

    row_number: int
    snapshot_id: str
    ticker: str
    as_of: str
    chain_path: Path
    chain_path_ref: str
    metadata_path: Path
    metadata_path_ref: str
    snapshot_source: str | None
    quote_observed_at: pd.Timestamp | None
    underlying_price: float | None
    underlying_price_observed_at: pd.Timestamp | None
    underlying_price_source: str | None
    expiration_start: pd.Timestamp | None
    expiration_end: pd.Timestamp | None


@dataclass(frozen=True)
class HistoricalSnapshot:
    """One normalized logical snapshot ready for scanner orchestration."""

    snapshot_id: str
    ticker: str
    as_of: str
    chain_path: Path
    chain_path_ref: str
    metadata_path: Path
    metadata_path_ref: str
    snapshot_source: str
    quote_observed_at: pd.Timestamp
    underlying_price: float
    underlying_price_observed_at: pd.Timestamp
    underlying_price_source: str
    expiration_start: pd.Timestamp
    expiration_end: pd.Timestamp
    metadata: dict[str, Any]
    option_quotes: pd.DataFrame


def _normalize_timestamp(value: Any) -> pd.Timestamp | None:
    """Parse one timestamp-like value into a timezone-naive pandas timestamp."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None

    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).tz_localize(None)


def _normalize_string(value: Any) -> str | None:
    """Return one trimmed string, or None when it is blank."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_numeric(value: Any) -> float | None:
    """Return one finite float, or None when the input is blank."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None

    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    numeric = float(parsed)
    return numeric if math.isfinite(numeric) else None


def _parse_required_timestamp(value: Any, *, row_number: int, label: str) -> pd.Timestamp:
    """Parse one required timestamp-like manifest or metadata value."""
    parsed = _normalize_timestamp(value)
    if parsed is None:
        raise ValueError(f"Manifest row {row_number} has invalid {label}: {value}")
    return parsed


def _parse_optional_timestamp(value: Any, *, row_number: int, label: str) -> pd.Timestamp | None:
    """Parse one optional timestamp-like manifest or metadata value."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    parsed = _normalize_timestamp(value)
    if parsed is None:
        raise ValueError(f"Manifest row {row_number} has invalid {label}: {value}")
    return parsed


def _parse_optional_numeric(value: Any, *, row_number: int, label: str) -> float | None:
    """Parse one optional numeric manifest or metadata value."""
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return None
    parsed = _normalize_numeric(value)
    if parsed is None:
        raise ValueError(f"Manifest row {row_number} has invalid {label}: {value}")
    return parsed


def _portable_path_ref(raw_path: str, resolved_path: Path, manifest_dir: Path) -> str:
    """Return one stable artifact reference without forcing machine-specific absolute paths."""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        return candidate.as_posix()

    try:
        return resolved_path.relative_to(manifest_dir).as_posix()
    except ValueError:
        return str(resolved_path)


def _normalize_path_key(path: Path) -> str:
    """Return one case-insensitive local path key for duplicate detection."""
    return str(path.resolve(strict=False)).casefold()


def _resolve_manifest_path(
    *,
    raw_path: Any,
    manifest_dir: Path,
    row_number: int,
    column: str,
) -> tuple[Path, str]:
    """Resolve one manifest-local artifact path and one portable reference."""
    path_text = _normalize_string(raw_path)
    if path_text is None:
        raise ValueError(f"Manifest row {row_number} has an empty {column}")

    candidate = Path(path_text)
    resolved = candidate if candidate.is_absolute() else (manifest_dir / candidate)
    resolved = resolved.resolve(strict=False)
    return resolved, _portable_path_ref(path_text, resolved, manifest_dir)


def _load_manifest_frame(manifest_path: str | Path) -> pd.DataFrame:
    """Load a historical snapshot manifest from local CSV or JSON."""
    path = Path(manifest_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        manifest = pd.read_csv(path)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        manifest = pd.DataFrame(payload)
    else:
        raise ValueError(f"Unsupported manifest file type: {path.suffix or '<no extension>'}")

    missing_columns = [
        column for column in HISTORICAL_SNAPSHOT_MANIFEST_REQUIRED_COLUMNS if column not in manifest.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required historical snapshot manifest columns: {missing}")

    return manifest.reset_index(drop=True)


def load_historical_snapshot_manifest_frame(manifest_path: str | Path) -> pd.DataFrame:
    """Load one raw historical snapshot manifest frame after schema validation."""
    return _load_manifest_frame(manifest_path)


def _read_metadata_payload(metadata_path: Path, *, row_number: int) -> dict[str, Any]:
    """Read one JSON metadata sidecar and require an object payload."""
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Manifest row {row_number} metadata file does not exist: {metadata_path}"
        )

    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Manifest row {row_number} metadata file is not valid JSON: {metadata_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"Manifest row {row_number} metadata file must contain one JSON object: {metadata_path}"
        )
    return payload


def _metadata_ticker(metadata: dict[str, Any]) -> str | None:
    """Return one normalized ticker label from known sidecar keys."""
    for key in ("ticker_normalized", "ticker", "symbol"):
        normalized = _normalize_string(metadata.get(key))
        if normalized is not None:
            return normalized.upper()
    return None


def _metadata_snapshot_source(metadata: dict[str, Any]) -> str | None:
    """Return one snapshot-level provenance source from known sidecar keys."""
    for key in (SNAPSHOT_SOURCE_COLUMN, "source_vendor", "source"):
        normalized = _normalize_string(metadata.get(key))
        if normalized is not None:
            return normalized
    return None


def _metadata_snapshot_id(metadata: dict[str, Any]) -> str | None:
    """Return one explicit metadata snapshot identifier when present."""
    return _normalize_string(metadata.get(SNAPSHOT_ID_COLUMN))


def _metadata_quote_observed_at(metadata: dict[str, Any], *, row_number: int) -> pd.Timestamp | None:
    """Return one metadata quote-observation timestamp when available."""
    return _parse_optional_timestamp(
        metadata.get(QUOTE_OBSERVED_AT_COLUMN, metadata.get("fetched_at_utc")),
        row_number=row_number,
        label=QUOTE_OBSERVED_AT_COLUMN,
    )


def _metadata_underlying_price_observed_at(
    metadata: dict[str, Any],
    *,
    row_number: int,
) -> pd.Timestamp | None:
    """Return one metadata spot-observation timestamp when available."""
    return _parse_optional_timestamp(
        metadata.get(UNDERLYING_PRICE_OBSERVED_AT_COLUMN),
        row_number=row_number,
        label=UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    )


def _metadata_expiration_bounds(
    metadata: dict[str, Any],
    *,
    row_number: int,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return optional expiration coverage bounds from one metadata payload."""
    expiration_start = _parse_optional_timestamp(
        metadata.get("expiration_start", metadata.get("expiration_resolved")),
        row_number=row_number,
        label="expiration_start",
    )
    expiration_end = _parse_optional_timestamp(
        metadata.get("expiration_end", metadata.get("expiration_resolved")),
        row_number=row_number,
        label="expiration_end",
    )
    return expiration_start, expiration_end


def _coalesce_required_value(
    *,
    field_name: str,
    manifest_value: Any,
    metadata_value: Any,
    row_number: int,
) -> Any:
    """Pick one authoritative explicit value and reject manifest/metadata conflicts."""
    if manifest_value is None and metadata_value is None:
        raise ValueError(
            f"Manifest row {row_number} is missing explicit {field_name} provenance "
            "in both the manifest row and the metadata sidecar."
        )
    if manifest_value is None:
        return metadata_value
    if metadata_value is None:
        return manifest_value

    if isinstance(manifest_value, pd.Timestamp) and isinstance(metadata_value, pd.Timestamp):
        if manifest_value != metadata_value:
            raise ValueError(
                f"Manifest row {row_number} disagrees with metadata for {field_name}: "
                f"{manifest_value} != {metadata_value}"
            )
        return manifest_value

    if isinstance(manifest_value, float) and isinstance(metadata_value, float):
        if abs(manifest_value - metadata_value) > 1e-9:
            raise ValueError(
                f"Manifest row {row_number} disagrees with metadata for {field_name}: "
                f"{manifest_value} != {metadata_value}"
            )
        return manifest_value

    if str(manifest_value).strip().casefold() != str(metadata_value).strip().casefold():
        raise ValueError(
            f"Manifest row {row_number} disagrees with metadata for {field_name}: "
            f"{manifest_value} != {metadata_value}"
        )
    return manifest_value


def _fill_timestamp_column(
    option_quotes: pd.DataFrame,
    *,
    column: str,
    value: pd.Timestamp,
) -> pd.DataFrame:
    """Fill one timestamp column with an authoritative value when rows are blank."""
    working = option_quotes.copy()
    if column not in working.columns:
        working[column] = value
        return working

    parsed = pd.to_datetime(working[column], errors="coerce", utc=True)
    normalized = parsed.dt.tz_localize(None)
    working[column] = normalized.where(normalized.notna(), value)
    return working


def _fill_string_column(option_quotes: pd.DataFrame, *, column: str, value: str) -> pd.DataFrame:
    """Fill one string column with an authoritative value when rows are blank."""
    working = option_quotes.copy()
    if column not in working.columns:
        working[column] = value
        return working

    existing = working[column].fillna("").astype("string").str.strip()
    working[column] = existing.where(existing.ne(""), value)
    return working


def _fill_numeric_column(option_quotes: pd.DataFrame, *, column: str, value: float) -> pd.DataFrame:
    """Fill one numeric column with an authoritative value when rows are blank."""
    working = option_quotes.copy()
    if column not in working.columns:
        working[column] = value
        return working

    numeric = pd.to_numeric(working[column], errors="coerce")
    working[column] = numeric.where(numeric.notna(), value)
    return working


def _resolve_consistent_timestamp(
    option_quotes: pd.DataFrame,
    *,
    column: str,
    row_number: int,
    snapshot_id: str,
) -> pd.Timestamp:
    """Return one unique non-null timestamp carried by a logical snapshot."""
    if column not in option_quotes.columns:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) is missing {column}."
        )

    timestamps = pd.to_datetime(option_quotes[column], errors="coerce", utc=True).dt.tz_localize(None)
    valid = timestamps.dropna()
    if valid.empty:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) has empty {column} provenance."
        )

    unique = valid.unique().tolist()
    if len(unique) != 1:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) carries multiple {column} values."
        )
    return pd.Timestamp(unique[0])


def _resolve_consistent_string(
    option_quotes: pd.DataFrame,
    *,
    column: str,
    row_number: int,
    snapshot_id: str,
) -> str:
    """Return one unique non-empty string carried by a logical snapshot."""
    if column not in option_quotes.columns:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) is missing {column}."
        )

    values = option_quotes[column].fillna("").astype("string").str.strip()
    values = values.loc[values.ne("")]
    if values.empty:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) has empty {column} provenance."
        )

    unique = values.unique().tolist()
    if len(unique) != 1:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) carries multiple {column} values."
        )
    return str(unique[0])


def _resolve_optional_consistent_string(option_quotes: pd.DataFrame, *, column: str) -> str | None:
    """Return one optional unique non-empty string, or None when the column is blank."""
    if column not in option_quotes.columns:
        return None

    values = option_quotes[column].fillna("").astype("string").str.strip()
    values = values.loc[values.ne("")]
    if values.empty:
        return None

    unique = values.unique().tolist()
    if len(unique) != 1:
        raise ValueError(f"Historical snapshot chain artifact carries multiple {column} values.")
    return str(unique[0])


def _resolve_consistent_numeric(
    option_quotes: pd.DataFrame,
    *,
    column: str,
    row_number: int,
    snapshot_id: str,
) -> float:
    """Return one unique numeric value carried by a logical snapshot."""
    if column not in option_quotes.columns:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) is missing {column}."
        )

    numeric = pd.to_numeric(option_quotes[column], errors="coerce").dropna()
    if numeric.empty:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) is missing {column}."
        )

    if float(numeric.max()) - float(numeric.min()) > 1e-9:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) carries multiple {column} values."
        )
    return float(numeric.iloc[0])


def _resolve_expiration_bounds_from_quotes(
    option_quotes: pd.DataFrame,
    *,
    row_number: int,
    snapshot_id: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return min/max expiration dates represented by one snapshot chain artifact."""
    expirations = pd.to_datetime(option_quotes["expiration"], errors="coerce").dropna()
    if expirations.empty:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) has no valid expiration values."
        )
    return expirations.min().normalize(), expirations.max().normalize()


def _assert_equal_timestamp(
    actual: pd.Timestamp,
    expected: pd.Timestamp,
    *,
    row_number: int,
    snapshot_id: str,
    label: str,
) -> None:
    """Reject timestamp mismatches between the chain artifact and authoritative provenance."""
    if actual != expected:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) has {label} "
            f"{actual}, expected {expected}."
        )


def _assert_equal_string(
    actual: str,
    expected: str,
    *,
    row_number: int,
    snapshot_id: str,
    label: str,
) -> None:
    """Reject string mismatches between the chain artifact and authoritative provenance."""
    if actual.strip().casefold() != expected.strip().casefold():
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) has {label} "
            f"{actual}, expected {expected}."
        )


def _assert_equal_numeric(
    actual: float,
    expected: float,
    *,
    row_number: int,
    snapshot_id: str,
    label: str,
) -> None:
    """Reject numeric mismatches between the chain artifact and authoritative provenance."""
    if abs(actual - expected) > 1e-9:
        raise ValueError(
            f"Historical snapshot {snapshot_id} (manifest row {row_number}) has {label} "
            f"{actual}, expected {expected}."
        )


def validate_historical_snapshot_manifest_row(
    row: pd.Series,
    *,
    row_number: int,
    manifest_dir: str | Path,
) -> HistoricalSnapshotSpec:
    """Validate one manifest row and return a resolved snapshot spec."""
    base_dir = Path(manifest_dir)
    snapshot_id = _normalize_string(row.get(SNAPSHOT_ID_COLUMN))
    ticker = _normalize_string(row.get("ticker"))
    as_of = _normalize_string(row.get("as_of"))
    if snapshot_id is None:
        raise ValueError(f"Manifest row {row_number} has an empty {SNAPSHOT_ID_COLUMN}")
    if ticker is None:
        raise ValueError(f"Manifest row {row_number} has an empty ticker")
    if as_of is None:
        raise ValueError(f"Manifest row {row_number} has an empty as_of")

    _parse_required_timestamp(as_of, row_number=row_number, label="as_of")
    chain_path, chain_path_ref = _resolve_manifest_path(
        raw_path=row.get("chain_path"),
        manifest_dir=base_dir,
        row_number=row_number,
        column="chain_path",
    )
    metadata_path, metadata_path_ref = _resolve_manifest_path(
        raw_path=row.get("metadata_path"),
        manifest_dir=base_dir,
        row_number=row_number,
        column="metadata_path",
    )

    return HistoricalSnapshotSpec(
        row_number=row_number,
        snapshot_id=snapshot_id,
        ticker=ticker.upper(),
        as_of=as_of,
        chain_path=chain_path,
        chain_path_ref=chain_path_ref,
        metadata_path=metadata_path,
        metadata_path_ref=metadata_path_ref,
        snapshot_source=_normalize_string(row.get(SNAPSHOT_SOURCE_COLUMN)),
        quote_observed_at=_parse_optional_timestamp(
            row.get(QUOTE_OBSERVED_AT_COLUMN),
            row_number=row_number,
            label=QUOTE_OBSERVED_AT_COLUMN,
        ),
        underlying_price=_parse_optional_numeric(
            row.get("underlying_price"),
            row_number=row_number,
            label="underlying_price",
        ),
        underlying_price_observed_at=_parse_optional_timestamp(
            row.get(UNDERLYING_PRICE_OBSERVED_AT_COLUMN),
            row_number=row_number,
            label=UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
        ),
        underlying_price_source=_normalize_string(row.get(UNDERLYING_PRICE_SOURCE_COLUMN)),
        expiration_start=_parse_optional_timestamp(
            row.get("expiration_start"),
            row_number=row_number,
            label="expiration_start",
        ),
        expiration_end=_parse_optional_timestamp(
            row.get("expiration_end"),
            row_number=row_number,
            label="expiration_end",
        ),
    )


def parse_historical_snapshot_manifest(manifest_path: str | Path) -> list[HistoricalSnapshotSpec]:
    """Parse and validate manifest rows into resolved snapshot specs."""
    manifest = _load_manifest_frame(manifest_path)
    manifest_dir = Path(manifest_path).resolve(strict=False).parent
    return [
        validate_historical_snapshot_manifest_row(
            row,
            row_number=index + 1,
            manifest_dir=manifest_dir,
        )
        for index, row in manifest.iterrows()
    ]


def collect_duplicate_snapshot_spec_errors(
    specs: Iterable[HistoricalSnapshotSpec],
) -> dict[int, str]:
    """Return row-numbered duplicate-identity and duplicate-artifact failures."""
    spec_list = list(specs)
    errors: dict[int, str] = {}

    duplicate_groups = {
        SNAPSHOT_ID_COLUMN: {},
        "chain_path": {},
        "metadata_path": {},
    }
    for spec in spec_list:
        duplicate_groups[SNAPSHOT_ID_COLUMN].setdefault(spec.snapshot_id.casefold(), []).append(spec)
        duplicate_groups["chain_path"].setdefault(_normalize_path_key(spec.chain_path), []).append(spec)
        duplicate_groups["metadata_path"].setdefault(_normalize_path_key(spec.metadata_path), []).append(spec)

    for key, grouped_specs in duplicate_groups.items():
        for group in grouped_specs.values():
            if len(group) < 2:
                continue

            row_numbers = ", ".join(str(spec.row_number) for spec in group)
            if key == SNAPSHOT_ID_COLUMN:
                message = (
                    f"Manifest rows {row_numbers} reuse the same {SNAPSHOT_ID_COLUMN} "
                    f"'{group[0].snapshot_id}'."
                )
            elif key == "chain_path":
                message = (
                    f"Manifest rows {row_numbers} resolve chain_path to the same local artifact: "
                    f"{group[0].chain_path}"
                )
            else:
                message = (
                    f"Manifest rows {row_numbers} resolve metadata_path to the same local artifact: "
                    f"{group[0].metadata_path}"
                )

            for spec in group:
                errors.setdefault(spec.row_number, message)

    return errors


def load_historical_snapshot(spec: HistoricalSnapshotSpec) -> HistoricalSnapshot:
    """Load one logical snapshot, enforce provenance, and normalize it for scanning."""
    row_number = spec.row_number
    if not spec.chain_path.exists():
        raise FileNotFoundError(
            f"Manifest row {row_number} chain file does not exist: {spec.chain_path}"
        )

    metadata = _read_metadata_payload(spec.metadata_path, row_number=row_number)
    metadata_snapshot_id = _metadata_snapshot_id(metadata)
    if metadata_snapshot_id is None:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) metadata "
            f"must include {SNAPSHOT_ID_COLUMN}."
        )
    if metadata_snapshot_id != spec.snapshot_id:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) metadata "
            f"{SNAPSHOT_ID_COLUMN} {metadata_snapshot_id} does not match the manifest value."
        )
    metadata_ticker = _metadata_ticker(metadata)
    if metadata_ticker is not None and metadata_ticker != spec.ticker:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) metadata ticker "
            f"{metadata_ticker} does not match manifest ticker {spec.ticker}."
        )

    snapshot_source = _coalesce_required_value(
        field_name=SNAPSHOT_SOURCE_COLUMN,
        manifest_value=spec.snapshot_source,
        metadata_value=_metadata_snapshot_source(metadata),
        row_number=row_number,
    )
    quote_observed_at = _coalesce_required_value(
        field_name=QUOTE_OBSERVED_AT_COLUMN,
        manifest_value=spec.quote_observed_at,
        metadata_value=_metadata_quote_observed_at(metadata, row_number=row_number),
        row_number=row_number,
    )
    underlying_price = _coalesce_required_value(
        field_name="underlying_price",
        manifest_value=spec.underlying_price,
        metadata_value=_parse_optional_numeric(
            metadata.get("underlying_price"),
            row_number=row_number,
            label="underlying_price",
        ),
        row_number=row_number,
    )
    underlying_price_observed_at = _coalesce_required_value(
        field_name=UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
        manifest_value=spec.underlying_price_observed_at,
        metadata_value=_metadata_underlying_price_observed_at(
            metadata,
            row_number=row_number,
        ),
        row_number=row_number,
    )
    underlying_price_source = _coalesce_required_value(
        field_name=UNDERLYING_PRICE_SOURCE_COLUMN,
        manifest_value=spec.underlying_price_source,
        metadata_value=_normalize_string(metadata.get(UNDERLYING_PRICE_SOURCE_COLUMN)),
        row_number=row_number,
    )

    if quote_observed_at != underlying_price_observed_at:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) must use the same "
            f"timestamp for {QUOTE_OBSERVED_AT_COLUMN} and {UNDERLYING_PRICE_OBSERVED_AT_COLUMN}; "
            f"received {quote_observed_at} and {underlying_price_observed_at}."
        )

    option_quotes = load_option_quotes(
        spec.chain_path,
        require_underlying_price=False,
        default_ticker=spec.ticker,
    )
    existing_chain_snapshot_id = _resolve_optional_consistent_string(
        option_quotes,
        column=SNAPSHOT_ID_COLUMN,
    )
    if existing_chain_snapshot_id is not None and existing_chain_snapshot_id != spec.snapshot_id:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) chain "
            f"{SNAPSHOT_ID_COLUMN} {existing_chain_snapshot_id} does not match the manifest value."
        )
    option_quotes = enrich_option_quote_provenance(
        option_quotes,
        input_path=spec.chain_path,
        metadata_path=spec.metadata_path,
        input_path_ref=spec.chain_path_ref,
        metadata_path_ref=spec.metadata_path_ref,
        snapshot_id=spec.snapshot_id,
        snapshot_source=str(snapshot_source),
    )
    option_quotes = _fill_timestamp_column(
        option_quotes,
        column=QUOTE_OBSERVED_AT_COLUMN,
        value=quote_observed_at,
    )
    option_quotes = _fill_timestamp_column(
        option_quotes,
        column=UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
        value=underlying_price_observed_at,
    )
    option_quotes = _fill_string_column(
        option_quotes,
        column=UNDERLYING_PRICE_SOURCE_COLUMN,
        value=str(underlying_price_source),
    )
    option_quotes = _fill_string_column(
        option_quotes,
        column=SNAPSHOT_SOURCE_COLUMN,
        value=str(snapshot_source),
    )
    option_quotes = _fill_numeric_column(
        option_quotes,
        column="underlying_price",
        value=float(underlying_price),
    )
    option_quotes = normalize_provenance_columns(option_quotes)

    chain_tickers = (
        option_quotes["ticker"].dropna().astype("string").str.strip().str.upper().unique().tolist()
    )
    if not chain_tickers:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) has no ticker values."
        )
    if len(chain_tickers) != 1 or chain_tickers[0] != spec.ticker:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) chain ticker "
            f"{chain_tickers} does not match manifest ticker {spec.ticker}."
        )

    resolved_quote_observed_at = _resolve_consistent_timestamp(
        option_quotes,
        column=QUOTE_OBSERVED_AT_COLUMN,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )
    resolved_underlying_price_observed_at = _resolve_consistent_timestamp(
        option_quotes,
        column=UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )
    resolved_underlying_price_source = _resolve_consistent_string(
        option_quotes,
        column=UNDERLYING_PRICE_SOURCE_COLUMN,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )
    resolved_snapshot_source = _resolve_consistent_string(
        option_quotes,
        column=SNAPSHOT_SOURCE_COLUMN,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )
    resolved_underlying_price = _resolve_consistent_numeric(
        option_quotes,
        column="underlying_price",
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )
    resolved_snapshot_id = _resolve_consistent_string(
        option_quotes,
        column=SNAPSHOT_ID_COLUMN,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )

    _assert_equal_string(
        resolved_snapshot_id,
        spec.snapshot_id,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
        label=SNAPSHOT_ID_COLUMN,
    )
    _assert_equal_timestamp(
        resolved_quote_observed_at,
        quote_observed_at,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
        label=QUOTE_OBSERVED_AT_COLUMN,
    )
    _assert_equal_timestamp(
        resolved_underlying_price_observed_at,
        underlying_price_observed_at,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
        label=UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    )
    _assert_equal_string(
        resolved_underlying_price_source,
        str(underlying_price_source),
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
        label=UNDERLYING_PRICE_SOURCE_COLUMN,
    )
    _assert_equal_string(
        resolved_snapshot_source,
        str(snapshot_source),
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
        label=SNAPSHOT_SOURCE_COLUMN,
    )
    _assert_equal_numeric(
        resolved_underlying_price,
        float(underlying_price),
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
        label="underlying_price",
    )

    if resolved_quote_observed_at != resolved_underlying_price_observed_at:
        raise ValueError(
            f"Historical snapshot {spec.snapshot_id} (manifest row {row_number}) combines "
            f"{QUOTE_OBSERVED_AT_COLUMN} {resolved_quote_observed_at} with "
            f"{UNDERLYING_PRICE_OBSERVED_AT_COLUMN} {resolved_underlying_price_observed_at}."
        )

    as_of_ts, as_of_day_precision = resolve_effective_as_of(option_quotes, explicit_as_of=spec.as_of)
    validate_point_in_time_integrity(
        option_quotes,
        as_of=as_of_ts,
        as_of_day_precision=as_of_day_precision,
        allow_unsafe_as_of=False,
    )

    metadata_expiration_start, metadata_expiration_end = _metadata_expiration_bounds(
        metadata,
        row_number=row_number,
    )
    expiration_start = _coalesce_required_value(
        field_name="expiration_start",
        manifest_value=spec.expiration_start,
        metadata_value=metadata_expiration_start,
        row_number=row_number,
    ) if spec.expiration_start is not None or metadata_expiration_start is not None else None
    expiration_end = _coalesce_required_value(
        field_name="expiration_end",
        manifest_value=spec.expiration_end,
        metadata_value=metadata_expiration_end,
        row_number=row_number,
    ) if spec.expiration_end is not None or metadata_expiration_end is not None else None

    resolved_expiration_start, resolved_expiration_end = _resolve_expiration_bounds_from_quotes(
        option_quotes,
        row_number=row_number,
        snapshot_id=spec.snapshot_id,
    )
    if expiration_start is not None:
        _assert_equal_timestamp(
            resolved_expiration_start,
            expiration_start.normalize(),
            row_number=row_number,
            snapshot_id=spec.snapshot_id,
            label="expiration_start",
        )
    if expiration_end is not None:
        _assert_equal_timestamp(
            resolved_expiration_end,
            expiration_end.normalize(),
            row_number=row_number,
            snapshot_id=spec.snapshot_id,
            label="expiration_end",
        )

    return HistoricalSnapshot(
        snapshot_id=spec.snapshot_id,
        ticker=spec.ticker,
        as_of=spec.as_of,
        chain_path=spec.chain_path,
        chain_path_ref=spec.chain_path_ref,
        metadata_path=spec.metadata_path,
        metadata_path_ref=spec.metadata_path_ref,
        snapshot_source=str(snapshot_source),
        quote_observed_at=resolved_quote_observed_at,
        underlying_price=resolved_underlying_price,
        underlying_price_observed_at=resolved_underlying_price_observed_at,
        underlying_price_source=resolved_underlying_price_source,
        expiration_start=resolved_expiration_start,
        expiration_end=resolved_expiration_end,
        metadata=metadata,
        option_quotes=option_quotes.reset_index(drop=True),
    )


def load_historical_snapshots(manifest_path: str | Path) -> list[HistoricalSnapshot]:
    """Load one historical snapshot manifest into strict per-snapshot scanner inputs."""
    specs = parse_historical_snapshot_manifest(manifest_path)
    duplicate_errors = collect_duplicate_snapshot_spec_errors(specs)
    if duplicate_errors:
        first_row = min(duplicate_errors)
        raise ValueError(duplicate_errors[first_row])

    return [load_historical_snapshot(spec) for spec in specs]
