"""Adapters for canonical Trading Foundation historical snapshot and EOD artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from options_edge_scanner.calibration.contracts import (
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    build_required_outcome_key,
    format_date_like,
    format_utc_timestamp,
)
from options_edge_scanner.calibration.materialization import (
    REQUIRED_OUTCOME_REQUEST_COLUMNS,
    collect_required_outcome_requests_from_manifest,
    partition_required_outcome_requests_by_realization,
)
from options_edge_scanner.calibration.terminal_semantics import (
    is_us_equity_trading_day,
    market_close_timestamp_for_event_date,
    resolve_terminal_observation_policy,
)
from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.data.provenance import (
    QUOTE_OBSERVED_AT_COLUMN,
    SNAPSHOT_ID_COLUMN,
    SNAPSHOT_SOURCE_COLUMN,
    UNDERLYING_PRICE_OBSERVED_AT_COLUMN,
    UNDERLYING_PRICE_SOURCE_COLUMN,
)
from options_edge_scanner.data.realized_underlying import (
    build_realized_underlying_artifact_id,
    build_realized_underlying_observation_id,
    validate_realized_underlying_frame,
    write_realized_underlying_frame,
)


TRADING_FOUNDATION_SNAPSHOT_SOURCE = "trading_foundation.option_snapshot"
TRADING_FOUNDATION_EOD_SOURCE = "trading_foundation"
TRADING_FOUNDATION_EOD_DATASET = "historical_data.eod"
TRADING_FOUNDATION_EOD_FEED = "canonical_local_file"
TRADING_FOUNDATION_EOD_TIMEFRAME = "1Day"
TRADING_FOUNDATION_EOD_UNDERLYING_PRICE_SOURCE = "trading_foundation.eod.close"
TRADING_FOUNDATION_SNAPSHOT_UNDERLYING_PRICE_SOURCE = "trading_foundation.option_snapshot.underlying_price"
TRADING_FOUNDATION_DAY_PRECISION_POLICY = "file_date_day_precision"

_OPTION_SNAPSHOT_FILENAME_PATTERN = re.compile(
    r"^(?P<ticker>[A-Z0-9]+)_options_snapshot_(?P<date>\d{4}-\d{2}-\d{2})\.csv$"
)


@dataclass(frozen=True)
class TradingFoundationManifestArtifacts:
    """Portable manifest bundle pointing at raw Trading Foundation snapshot files."""

    manifest_path: Path
    metadata_paths: tuple[Path, ...]
    snapshot_dates: tuple[str, ...]


@dataclass(frozen=True)
class TradingFoundationRealizedOutcomeCoverage:
    """Manifest-derived realized versus future expiration coverage for Trading Foundation exports."""

    required_observations: pd.DataFrame
    eligible_required_observations: pd.DataFrame
    future_required_observations: pd.DataFrame
    realized_as_of: pd.Timestamp


@dataclass(frozen=True)
class TradingFoundationEodCoverageAudit:
    """Coverage audit for one set of requested Trading Foundation EOD event dates."""

    requested_event_dates: tuple[str, ...]
    available_event_dates: tuple[str, ...]
    missing_event_dates: tuple[str, ...]
    audit_rows: pd.DataFrame


def _normalize_date(value: object, *, label: str) -> pd.Timestamp:
    """Parse one date-like value into a normalized timestamp."""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{label} must be a valid YYYY-MM-DD date, received: {value}")
    return pd.Timestamp(parsed).normalize()


def _normalize_timestamp(value: object) -> pd.Timestamp | None:
    """Parse one timestamp-like value into a timezone-naive UTC timestamp."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).tz_localize(None)


def _parse_mixed_utc_timestamp_series(values: pd.Series) -> pd.Series:
    """Parse one timestamp series while tolerating mixed-but-valid source formats."""
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    if values.empty or parsed.notna().all():
        return parsed

    fallback_mask = values.notna() & parsed.isna()
    if not fallback_mask.any():
        return parsed

    fallback_parsed = values.loc[fallback_mask].map(
        lambda value: pd.to_datetime(value, errors="coerce", utc=True)
    )
    reparsed = pd.to_datetime(fallback_parsed, errors="coerce", utc=True)
    repaired = parsed.copy()
    repaired.loc[fallback_mask] = reparsed
    return repaired


def _normalize_event_dates(event_dates: Sequence[object]) -> list[pd.Timestamp]:
    """Normalize one explicit set of required event dates."""
    return sorted({_normalize_date(value, label="event_date") for value in event_dates})


def _stringify_path_for_manifest(path: Path, *, manifest_dir: Path) -> str:
    """Serialize one path for manifest storage, preferring relative paths when possible."""
    try:
        return path.resolve(strict=False).relative_to(manifest_dir.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _require_symbol_root(historical_data_root: str | Path, *, ticker: str) -> Path:
    """Resolve one Trading Foundation symbol root and require it to exist."""
    root = Path(historical_data_root).resolve(strict=False)
    symbol_root = root / str(ticker).strip().upper()
    if not symbol_root.is_dir():
        raise FileNotFoundError(
            f"Trading Foundation symbol folder does not exist for ticker={ticker}: {symbol_root}"
        )
    return symbol_root


def _option_snapshot_dir(historical_data_root: str | Path, *, ticker: str) -> Path:
    """Return one canonical option_snapshot folder path."""
    return _require_symbol_root(historical_data_root, ticker=ticker) / "option_snapshot"


def _eod_path(historical_data_root: str | Path, *, ticker: str) -> Path:
    """Return one canonical EOD file path."""
    normalized_ticker = str(ticker).strip().upper()
    return _require_symbol_root(historical_data_root, ticker=normalized_ticker) / "eod" / f"{normalized_ticker}_1D.csv"


def _resolve_snapshot_path(
    historical_data_root: str | Path,
    *,
    ticker: str,
    snapshot_date: object,
) -> Path:
    """Resolve one canonical option snapshot file path."""
    normalized_ticker = str(ticker).strip().upper()
    normalized_date = format_date_like(snapshot_date)
    path = _option_snapshot_dir(historical_data_root, ticker=normalized_ticker) / (
        f"{normalized_ticker}_options_snapshot_{normalized_date}.csv"
    )
    if not path.is_file():
        raise FileNotFoundError(
            f"Trading Foundation option snapshot file does not exist: {path}"
        )
    return path


def _load_eod_frame(historical_data_root: str | Path, *, ticker: str) -> pd.DataFrame:
    """Load one canonical EOD file and normalize its timestamp column."""
    path = _eod_path(historical_data_root, ticker=ticker)
    if not path.is_file():
        raise FileNotFoundError(f"Trading Foundation EOD file does not exist: {path}")

    frame = pd.read_csv(path)
    missing = [column for column in ("close", "t") if column not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Trading Foundation EOD file is missing required columns: {joined}")

    working = frame.copy()
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    working["t"] = _parse_mixed_utc_timestamp_series(working["t"])
    working = working.dropna(subset=["close", "t"]).copy()
    working["t"] = working["t"].dt.tz_localize(None)
    working["session_date"] = working["t"].dt.normalize()
    return working.sort_values("t", kind="stable").reset_index(drop=True)


def _load_eod_audit_frame(historical_data_root: str | Path, *, ticker: str) -> pd.DataFrame:
    """Load one canonical EOD file with raw-versus-normalized audit columns preserved."""
    path = _eod_path(historical_data_root, ticker=ticker)
    if not path.is_file():
        raise FileNotFoundError(f"Trading Foundation EOD file does not exist: {path}")

    frame = pd.read_csv(path)
    missing = [column for column in ("close", "t") if column not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Trading Foundation EOD file is missing required columns: {joined}")

    working = frame.copy()
    working["_close_numeric"] = pd.to_numeric(working["close"], errors="coerce")
    working["_t_parsed"] = _parse_mixed_utc_timestamp_series(working["t"])
    parsed_mask = working["_t_parsed"].notna()
    working["_session_date"] = pd.NaT
    working.loc[parsed_mask, "_session_date"] = (
        working.loc[parsed_mask, "_t_parsed"].dt.tz_localize(None).dt.normalize()
    )
    working["_row_valid_for_normalized_eod"] = (
        working["_close_numeric"].notna() & working["_t_parsed"].notna()
    )
    return working


def audit_trading_foundation_eod_coverage(
    historical_data_root: str | Path,
    *,
    ticker: str,
    event_dates: Sequence[object],
) -> TradingFoundationEodCoverageAudit:
    """Audit whether requested realized-outcome dates are present in canonical EOD coverage."""
    normalized_event_dates = _normalize_event_dates(event_dates)
    if not normalized_event_dates:
        empty = pd.DataFrame(
            columns=[
                "event_date",
                "is_regular_us_equity_trading_day",
                "raw_rows_for_session_date",
                "valid_rows_for_session_date",
                "status",
                "issue_classification",
                "previous_available_event_date",
                "next_available_event_date",
            ]
        )
        return TradingFoundationEodCoverageAudit(
            requested_event_dates=(),
            available_event_dates=(),
            missing_event_dates=(),
            audit_rows=empty,
        )

    audit_frame = _load_eod_audit_frame(historical_data_root, ticker=ticker)
    valid_session_dates = sorted(
        {
            pd.Timestamp(value).normalize()
            for value in audit_frame.loc[audit_frame["_row_valid_for_normalized_eod"], "_session_date"].dropna()
        }
    )
    valid_session_date_strings = {format_date_like(value) for value in valid_session_dates}

    records: list[dict[str, object]] = []
    available_dates: list[str] = []
    missing_dates: list[str] = []
    for event_date in normalized_event_dates:
        event_date_string = format_date_like(event_date)
        matching_rows = audit_frame.loc[audit_frame["_session_date"] == event_date].copy()
        raw_rows_for_session_date = int(len(matching_rows))
        valid_rows_for_session_date = int(matching_rows["_row_valid_for_normalized_eod"].sum())
        is_trading_day = bool(is_us_equity_trading_day(event_date))
        previous_available = next(
            (format_date_like(value) for value in reversed(valid_session_dates) if value < event_date),
            "",
        )
        next_available = next(
            (format_date_like(value) for value in valid_session_dates if value > event_date),
            "",
        )

        if valid_rows_for_session_date > 0:
            status = "available"
            issue_classification = ""
            available_dates.append(event_date_string)
        else:
            status = "missing"
            missing_dates.append(event_date_string)
            if raw_rows_for_session_date > 0:
                issue_classification = "raw_row_present_but_invalid_close_or_timestamp"
            elif not is_trading_day:
                issue_classification = "non_trading_day_no_explicit_roll_convention"
            else:
                issue_classification = "trading_day_absent_from_canonical_eod"

        records.append(
            {
                "event_date": event_date_string,
                "is_regular_us_equity_trading_day": is_trading_day,
                "raw_rows_for_session_date": raw_rows_for_session_date,
                "valid_rows_for_session_date": valid_rows_for_session_date,
                "status": status,
                "issue_classification": issue_classification,
                "previous_available_event_date": previous_available,
                "next_available_event_date": next_available,
            }
        )

    return TradingFoundationEodCoverageAudit(
        requested_event_dates=tuple(format_date_like(value) for value in normalized_event_dates),
        available_event_dates=tuple(sorted(set(available_dates))),
        missing_event_dates=tuple(sorted(set(missing_dates))),
        audit_rows=pd.DataFrame.from_records(records),
    )


def _format_eod_coverage_audit_message(audit: TradingFoundationEodCoverageAudit) -> str:
    """Render one concise message describing why requested EOD dates are unavailable."""
    if not audit.missing_event_dates:
        return ""

    detail_parts: list[str] = []
    audit_rows = audit.audit_rows.set_index("event_date", drop=False) if not audit.audit_rows.empty else pd.DataFrame()
    for event_date in audit.missing_event_dates:
        row = audit_rows.loc[event_date]
        detail_parts.append(
            (
                f"{event_date}("
                f"trading_day={bool(row['is_regular_us_equity_trading_day'])}, "
                f"raw_rows={int(row['raw_rows_for_session_date'])}, "
                f"valid_rows={int(row['valid_rows_for_session_date'])}, "
                f"classification={row['issue_classification']}, "
                f"prev_available={row['previous_available_event_date'] or 'none'}, "
                f"next_available={row['next_available_event_date'] or 'none'}"
                f")"
            )
        )
    return (
        "Trading Foundation EOD coverage is missing realized event dates: "
        f"{', '.join(audit.missing_event_dates)}. "
        "Coverage audit: "
        f"{'; '.join(detail_parts)}"
    )


def list_trading_foundation_snapshot_dates(
    historical_data_root: str | Path,
    *,
    ticker: str,
) -> list[pd.Timestamp]:
    """List available canonical option snapshot dates for one ticker."""
    directory = _option_snapshot_dir(historical_data_root, ticker=ticker)
    if not directory.is_dir():
        raise FileNotFoundError(
            f"Trading Foundation option_snapshot folder does not exist: {directory}"
        )

    dates: list[pd.Timestamp] = []
    for path in sorted(directory.glob(f"{str(ticker).strip().upper()}_options_snapshot_*.csv")):
        match = _OPTION_SNAPSHOT_FILENAME_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        dates.append(_normalize_date(match.group("date"), label="snapshot filename date"))
    return sorted(set(dates))


def _resolve_requested_snapshot_dates(
    historical_data_root: str | Path,
    *,
    ticker: str,
    snapshot_dates: Sequence[object] | None,
    start_date: object | None,
    end_date: object | None,
) -> list[pd.Timestamp]:
    """Resolve an explicit or range-based snapshot-date request."""
    explicit_dates = [_normalize_date(value, label="snapshot_date") for value in (snapshot_dates or [])]
    if explicit_dates:
        return sorted(set(explicit_dates))

    if start_date is None and end_date is None:
        raise ValueError(
            "Provide at least one --snapshot-date or a --start-date/--end-date range."
        )

    available_dates = list_trading_foundation_snapshot_dates(
        historical_data_root,
        ticker=ticker,
    )
    if not available_dates:
        return []

    lower_bound = _normalize_date(start_date or available_dates[0], label="start_date")
    upper_bound = _normalize_date(end_date or available_dates[-1], label="end_date")
    if lower_bound > upper_bound:
        raise ValueError("start_date must be on or before end_date.")

    return [date for date in available_dates if lower_bound <= date <= upper_bound]


def build_trading_foundation_snapshot_id(*, ticker: str, snapshot_date: object) -> str:
    """Build one stable snapshot identifier for a canonical Trading Foundation daily file."""
    normalized_ticker = str(ticker).strip().upper()
    normalized_date = format_date_like(snapshot_date).replace("-", "")
    return f"tf-{normalized_ticker.lower()}-{normalized_date}"


def _resolve_snapshot_quote_observed_at(
    raw_snapshot: pd.DataFrame,
    *,
    snapshot_date: pd.Timestamp,
) -> tuple[str, str]:
    """Resolve one strict snapshot timestamp or day-precision marker."""
    for column in ("quote_observed_at", "snapshot_timestamp", "observed_at", "timestamp"):
        if column not in raw_snapshot.columns:
            continue

        parsed = pd.to_datetime(raw_snapshot[column], errors="coerce", utc=True).dropna()
        unique = parsed.unique().tolist()
        if len(unique) == 1:
            return format_utc_timestamp(unique[0]), f"{column}_uniform_full_timestamp"

    return format_date_like(snapshot_date), TRADING_FOUNDATION_DAY_PRECISION_POLICY


def _resolve_snapshot_underlying_price(
    option_quotes: pd.DataFrame,
    *,
    eod_frame: pd.DataFrame,
    snapshot_date: pd.Timestamp,
) -> tuple[float, str, str | None]:
    """Resolve the underlying spot value used for one snapshot manifest row."""
    if "underlying_price" in option_quotes.columns:
        numeric = pd.to_numeric(option_quotes["underlying_price"], errors="coerce").dropna()
        if not numeric.empty and float(numeric.max()) - float(numeric.min()) <= 1e-9:
            return (
                float(numeric.iloc[0]),
                TRADING_FOUNDATION_SNAPSHOT_UNDERLYING_PRICE_SOURCE,
                None,
            )

    matching = eod_frame.loc[eod_frame["session_date"] == snapshot_date]
    if matching.empty:
        raise ValueError(
            "Trading Foundation EOD coverage is missing the snapshot-date close needed for "
            f"ticker={option_quotes['ticker'].iloc[0] if 'ticker' in option_quotes.columns and not option_quotes.empty else ''} "
            f"date={format_date_like(snapshot_date)}."
        )
    if len(matching) != 1:
        raise ValueError(
            f"Trading Foundation EOD file contains multiple rows for date={format_date_like(snapshot_date)}."
        )

    row = matching.iloc[0]
    return (
        float(row["close"]),
        TRADING_FOUNDATION_EOD_UNDERLYING_PRICE_SOURCE,
        format_utc_timestamp(row["t"]),
    )


def _expiration_bounds(option_quotes: pd.DataFrame) -> tuple[str, str]:
    """Return min/max expiration strings represented by one normalized option-quote frame."""
    expirations = pd.to_datetime(option_quotes["expiration"], errors="coerce").dropna()
    if expirations.empty:
        raise ValueError("Trading Foundation snapshot did not yield any valid expiration values.")
    return format_date_like(expirations.min()), format_date_like(expirations.max())


def _build_snapshot_metadata(
    historical_data_root: str | Path,
    *,
    ticker: str,
    snapshot_date: pd.Timestamp,
    snapshot_path: Path,
) -> dict[str, object]:
    """Build one strict metadata sidecar for a canonical Trading Foundation snapshot file."""
    raw_snapshot = pd.read_csv(snapshot_path)
    option_quotes = load_option_quotes(
        snapshot_path,
        require_underlying_price=False,
        default_ticker=str(ticker).strip().upper(),
    )
    eod_frame = _load_eod_frame(historical_data_root, ticker=ticker)
    quote_observed_at, quote_policy = _resolve_snapshot_quote_observed_at(
        raw_snapshot,
        snapshot_date=snapshot_date,
    )
    underlying_price, underlying_price_source, raw_underlying_timestamp = _resolve_snapshot_underlying_price(
        option_quotes,
        eod_frame=eod_frame,
        snapshot_date=snapshot_date,
    )
    expiration_start, expiration_end = _expiration_bounds(option_quotes)
    snapshot_id = build_trading_foundation_snapshot_id(
        ticker=ticker,
        snapshot_date=snapshot_date,
    )

    metadata: dict[str, object] = {
        SNAPSHOT_ID_COLUMN: snapshot_id,
        SNAPSHOT_SOURCE_COLUMN: TRADING_FOUNDATION_SNAPSHOT_SOURCE,
        "source_vendor": TRADING_FOUNDATION_EOD_SOURCE,
        "ticker_normalized": str(ticker).strip().upper(),
        QUOTE_OBSERVED_AT_COLUMN: quote_observed_at,
        "quote_observed_at_policy": quote_policy,
        "underlying_price": underlying_price,
        UNDERLYING_PRICE_OBSERVED_AT_COLUMN: quote_observed_at,
        UNDERLYING_PRICE_SOURCE_COLUMN: underlying_price_source,
        "expiration_start": expiration_start,
        "expiration_end": expiration_end,
        "trading_foundation_historical_data_root": str(Path(historical_data_root).resolve(strict=False)),
        "raw_option_snapshot_path": str(snapshot_path.resolve(strict=False)),
        "raw_snapshot_date": format_date_like(snapshot_date),
    }
    if raw_underlying_timestamp is not None:
        metadata["underlying_price_raw_timestamp"] = raw_underlying_timestamp
    return metadata


def write_trading_foundation_snapshot_manifest(
    historical_data_root: str | Path,
    *,
    ticker: str,
    manifest_output_path: str | Path,
    snapshot_dates: Sequence[object] | None = None,
    start_date: object | None = None,
    end_date: object | None = None,
    metadata_dir: str | Path | None = None,
) -> TradingFoundationManifestArtifacts:
    """Write one strict manifest and metadata bundle pointing at raw Trading Foundation snapshots."""
    normalized_ticker = str(ticker).strip().upper()
    requested_dates = _resolve_requested_snapshot_dates(
        historical_data_root,
        ticker=normalized_ticker,
        snapshot_dates=snapshot_dates,
        start_date=start_date,
        end_date=end_date,
    )
    if not requested_dates:
        raise ValueError(
            f"No Trading Foundation option snapshot files were selected for ticker={normalized_ticker}."
        )

    manifest_path = Path(manifest_output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_root = (
        Path(metadata_dir)
        if metadata_dir is not None
        else manifest_path.parent / f"{manifest_path.stem}_metadata"
    )
    metadata_root.mkdir(parents=True, exist_ok=True)
    manifest_dir = manifest_path.parent.resolve(strict=False)

    metadata_paths: list[Path] = []
    manifest_rows: list[dict[str, object]] = []
    for snapshot_date in requested_dates:
        snapshot_path = _resolve_snapshot_path(
            historical_data_root,
            ticker=normalized_ticker,
            snapshot_date=snapshot_date,
        )
        metadata = _build_snapshot_metadata(
            historical_data_root,
            ticker=normalized_ticker,
            snapshot_date=snapshot_date,
            snapshot_path=snapshot_path,
        )
        snapshot_id = str(metadata[SNAPSHOT_ID_COLUMN])
        metadata_path = metadata_root / f"{snapshot_id}.meta.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        metadata_paths.append(metadata_path)
        manifest_rows.append(
            {
                SNAPSHOT_ID_COLUMN: snapshot_id,
                "ticker": normalized_ticker,
                "as_of": format_date_like(snapshot_date),
                "chain_path": _stringify_path_for_manifest(snapshot_path, manifest_dir=manifest_dir),
                "metadata_path": _stringify_path_for_manifest(metadata_path, manifest_dir=manifest_dir),
            }
        )

    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)
    return TradingFoundationManifestArtifacts(
        manifest_path=manifest_path.resolve(strict=False),
        metadata_paths=tuple(path.resolve(strict=False) for path in metadata_paths),
        snapshot_dates=tuple(format_date_like(value) for value in requested_dates),
    )


def collect_trading_foundation_realized_outcome_coverage(
    manifest_path: str | Path,
    *,
    realized_as_of: object | None = None,
) -> TradingFoundationRealizedOutcomeCoverage:
    """Collect manifest-derived realized-versus-future expiration coverage for calibration."""
    required_observations = collect_required_outcome_requests_from_manifest(manifest_path)
    partition = partition_required_outcome_requests_by_realization(
        required_observations,
        realized_as_of=realized_as_of,
    )
    return TradingFoundationRealizedOutcomeCoverage(
        required_observations=required_observations,
        eligible_required_observations=partition.eligible_required_observations,
        future_required_observations=partition.future_required_observations,
        realized_as_of=partition.realized_as_of,
    )


def normalize_trading_foundation_eod_to_realized_underlying(
    historical_data_root: str | Path,
    *,
    ticker: str,
    start_date: object | None = None,
    end_date: object | None = None,
    event_dates: Sequence[object] | None = None,
    required_outcome_horizon: str = "expiration",
    adjustment_mode: str = "unknown",
    acquired_at: object | None = None,
) -> pd.DataFrame:
    """Normalize Trading Foundation EOD bars into RealizedUnderlyingObservationRow records."""
    normalized_ticker = str(ticker).strip().upper()
    normalized_event_dates = _normalize_event_dates(event_dates or [])
    if normalized_event_dates:
        lower_bound = normalized_event_dates[0]
        upper_bound = normalized_event_dates[-1]
    else:
        if start_date is None or end_date is None:
            raise ValueError("Provide start_date/end_date or one or more explicit event_dates.")
        lower_bound = _normalize_date(start_date, label="start_date")
        upper_bound = _normalize_date(end_date, label="end_date")
        if lower_bound > upper_bound:
            raise ValueError("start_date must be on or before end_date.")

    policy = resolve_terminal_observation_policy(
        ticker=normalized_ticker,
        required_outcome_horizon=required_outcome_horizon,
    )
    eod_frame = _load_eod_frame(historical_data_root, ticker=normalized_ticker)
    if normalized_event_dates:
        bounded = eod_frame.loc[eod_frame["session_date"].isin(normalized_event_dates)].copy()
    else:
        bounded = eod_frame.loc[
            eod_frame["session_date"].between(lower_bound, upper_bound)
        ].copy()
    if bounded.empty:
        raise ValueError(
            "Trading Foundation EOD coverage is empty for "
            f"ticker={normalized_ticker}, start={format_date_like(lower_bound)}, "
            f"end={format_date_like(upper_bound)}."
        )
    if normalized_event_dates:
        requested_dates = {format_date_like(value) for value in normalized_event_dates}
        available_dates = set(bounded["session_date"].map(format_date_like).tolist())
        missing_dates = sorted(requested_dates.difference(available_dates))
        if missing_dates:
            audit = audit_trading_foundation_eod_coverage(
                historical_data_root,
                ticker=normalized_ticker,
                event_dates=normalized_event_dates,
            )
            raise ValueError(_format_eod_coverage_audit_message(audit))

    acquired_timestamp = (
        format_utc_timestamp(acquired_at)
        if acquired_at is not None
        else format_utc_timestamp(pd.Timestamp.now(tz="UTC"))
    )
    artifact_id = build_realized_underlying_artifact_id(
        source=TRADING_FOUNDATION_EOD_SOURCE,
        ticker=normalized_ticker,
        start=lower_bound,
        end=upper_bound,
        timeframe=TRADING_FOUNDATION_EOD_TIMEFRAME,
        adjustment_mode=adjustment_mode,
        source_feed=TRADING_FOUNDATION_EOD_FEED,
        terminal_price_convention=policy.terminal_price_convention,
    )

    records: list[dict[str, object]] = []
    for row in bounded.to_dict("records"):
        event_date = pd.Timestamp(row["session_date"]).normalize()
        market_close_timestamp = market_close_timestamp_for_event_date(
            event_date,
            policy=policy,
        )
        required_outcome_key = build_required_outcome_key(
            ticker=normalized_ticker,
            expiration=event_date,
            required_outcome_horizon=required_outcome_horizon,
            realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
        )
        records.append(
            {
                "observation_id": build_realized_underlying_observation_id(
                    ticker=normalized_ticker,
                    event_date=event_date,
                    required_outcome_horizon=required_outcome_horizon,
                    realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
                    terminal_price_convention=policy.terminal_price_convention,
                    terminal_price_convention_version=policy.terminal_price_convention_version,
                    source=TRADING_FOUNDATION_EOD_SOURCE,
                    source_dataset=TRADING_FOUNDATION_EOD_DATASET,
                    source_feed=TRADING_FOUNDATION_EOD_FEED,
                    timeframe=TRADING_FOUNDATION_EOD_TIMEFRAME,
                    adjustment_mode=adjustment_mode,
                ),
                "required_outcome_key": required_outcome_key,
                "ticker": normalized_ticker,
                "event_date": format_date_like(event_date),
                "required_outcome_horizon": required_outcome_horizon,
                "realized_outcome_measure": TERMINAL_UNDERLYING_OUTCOME_MEASURE,
                "terminal_price_convention": policy.terminal_price_convention,
                "terminal_price_convention_version": policy.terminal_price_convention_version,
                "observed_price": float(row["close"]),
                "observed_at": market_close_timestamp,
                "market_close_timestamp": market_close_timestamp,
                "price_field": policy.price_field,
                "observed_market_session": policy.observed_market_session,
                "source": TRADING_FOUNDATION_EOD_SOURCE,
                "source_dataset": TRADING_FOUNDATION_EOD_DATASET,
                "source_feed": TRADING_FOUNDATION_EOD_FEED,
                "timeframe": TRADING_FOUNDATION_EOD_TIMEFRAME,
                "adjustment_mode": adjustment_mode,
                "acquired_at": acquired_timestamp,
                "provenance_artifact_id": artifact_id,
                "source_bar_timestamp": format_utc_timestamp(row["t"]),
                "provider_symbol": normalized_ticker,
            }
        )

    return validate_realized_underlying_frame(pd.DataFrame.from_records(records))


def normalize_trading_foundation_eod_to_realized_underlying_for_manifest(
    historical_data_root: str | Path,
    *,
    ticker: str,
    manifest_path: str | Path,
    realized_as_of: object | None = None,
    required_outcome_horizon: str = "expiration",
    adjustment_mode: str = "unknown",
    acquired_at: object | None = None,
) -> tuple[pd.DataFrame, TradingFoundationRealizedOutcomeCoverage]:
    """Normalize only already-realized manifest-required event dates into realized-underlying rows."""
    coverage = collect_trading_foundation_realized_outcome_coverage(
        manifest_path,
        realized_as_of=realized_as_of,
    )
    if coverage.eligible_required_observations.empty:
        raise ValueError(
            "The manifest contains no already-realized required expiration outcomes as of "
            f"{format_utc_timestamp(coverage.realized_as_of)}."
        )

    manifest_tickers = (
        coverage.eligible_required_observations["ticker"].dropna().astype("string").str.strip().str.upper().unique().tolist()
    )
    normalized_ticker = str(ticker).strip().upper()
    if manifest_tickers and (len(manifest_tickers) != 1 or manifest_tickers[0] != normalized_ticker):
        raise ValueError(
            "Manifest-required outcome ticker coverage does not match the requested Trading Foundation export "
            f"ticker. manifest_tickers={manifest_tickers}, requested_ticker={normalized_ticker}"
        )

    observations = normalize_trading_foundation_eod_to_realized_underlying(
        historical_data_root,
        ticker=normalized_ticker,
        event_dates=coverage.eligible_required_observations["expiration"].tolist(),
        required_outcome_horizon=required_outcome_horizon,
        adjustment_mode=adjustment_mode,
        acquired_at=acquired_at,
    )
    return observations, coverage


def write_trading_foundation_realized_underlying(
    historical_data_root: str | Path,
    *,
    ticker: str,
    start_date: object | None = None,
    end_date: object | None = None,
    output_path: str | Path,
    manifest_path: str | Path | None = None,
    realized_as_of: object | None = None,
    required_outcome_horizon: str = "expiration",
    adjustment_mode: str = "unknown",
    acquired_at: object | None = None,
) -> pd.DataFrame:
    """Normalize and persist Trading Foundation EOD bars into one realized-underlying artifact."""
    if manifest_path is not None:
        observations, _coverage = normalize_trading_foundation_eod_to_realized_underlying_for_manifest(
            historical_data_root,
            ticker=ticker,
            manifest_path=manifest_path,
            realized_as_of=realized_as_of,
            required_outcome_horizon=required_outcome_horizon,
            adjustment_mode=adjustment_mode,
            acquired_at=acquired_at,
        )
    else:
        observations = normalize_trading_foundation_eod_to_realized_underlying(
            historical_data_root,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            required_outcome_horizon=required_outcome_horizon,
            adjustment_mode=adjustment_mode,
            acquired_at=acquired_at,
        )
    write_realized_underlying_frame(observations, output_path)
    return observations
