"""Optional Yahoo Finance option-chain ingestion for offline scanner artifacts."""

from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from options_edge_scanner.data.loader import OPTION_QUOTE_REQUIRED_COLUMNS, validate_option_quote_frame


DEFAULT_OUTPUT_ROOT = Path("outputs") / "yahoo_option_chains"
DEFAULT_CACHE_ROOT = DEFAULT_OUTPUT_ROOT / "cache"
INGESTION_VERSION = "1"
RAW_REQUIRED_COLUMNS = ("strike", "bid", "ask", "impliedVolatility")


class YahooIngestionError(RuntimeError):
    """Base error for Yahoo ingestion failures."""


@dataclass(frozen=True)
class YahooIngestionResult:
    """Summary of one Yahoo ingestion artifact write."""

    csv_path: Path
    metadata_path: Path
    metadata: dict[str, Any]


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _import_yfinance() -> Any:
    """Import yfinance lazily for optional Yahoo ingestion only."""
    try:
        return importlib.import_module("yfinance")
    except ImportError as exc:
        raise YahooIngestionError(
            "Yahoo ingestion requires the optional 'yfinance' dependency. "
            "Install it before running this command."
        ) from exc


def _normalize_ticker(ticker: str) -> str:
    """Validate and normalize a ticker symbol."""
    normalized = str(ticker).strip().upper()
    if not normalized:
        raise YahooIngestionError("Ticker must be a non-empty string.")
    return normalized


def _parse_expiration(expiration: str) -> pd.Timestamp:
    """Parse an explicit expiration date."""
    parsed = pd.to_datetime(expiration, errors="coerce")
    if pd.isna(parsed):
        raise YahooIngestionError(
            f"Expiration must be 'nearest' or a valid YYYY-MM-DD date, got: {expiration}"
        )
    return parsed.normalize()


def _resolve_expiration(available_expirations: list[str], requested_expiration: str) -> str:
    """Resolve an explicit or nearest expiration selector."""
    if not available_expirations:
        raise YahooIngestionError("Yahoo returned no option expirations for the requested ticker.")

    normalized_requested = str(requested_expiration).strip().lower()
    if normalized_requested == "nearest":
        resolved = min(pd.to_datetime(available_expirations, errors="coerce").dropna())
        return resolved.strftime("%Y-%m-%d")

    parsed_requested = _parse_expiration(requested_expiration).strftime("%Y-%m-%d")
    if parsed_requested not in available_expirations:
        available = ", ".join(available_expirations)
        raise YahooIngestionError(
            f"Requested expiration {parsed_requested} is not available for the requested ticker. "
            f"Available expirations: {available}"
        )
    return parsed_requested


def _default_output_path(ticker: str, resolved_expiration: str) -> Path:
    """Build the deterministic default normalized CSV path."""
    return DEFAULT_OUTPUT_ROOT / ticker / f"{ticker}_{resolved_expiration}_yahoo.csv"


def _build_snapshot_id(ticker: str, resolved_expiration: str, quote_observed_at: str) -> str:
    """Build one stable snapshot identifier for locally persisted Yahoo artifacts."""
    parsed_quote_observed_at = pd.to_datetime(quote_observed_at, errors="coerce", utc=True)
    if pd.isna(parsed_quote_observed_at):
        normalized_timestamp = quote_observed_at.replace(":", "").replace("-", "").replace(".", "")
    else:
        normalized_timestamp = parsed_quote_observed_at.strftime(
            "%Y%m%dT%H%M%S.%fZ" if parsed_quote_observed_at.microsecond else "%Y%m%dT%H%M%SZ"
        )
    return f"{ticker}_{normalized_timestamp}_{resolved_expiration}"


def _resolve_output_path(
    *,
    ticker: str,
    resolved_expiration: str,
    output_path: str | Path | None,
    output_dir: str | Path | None,
) -> Path:
    """Resolve a safe normalized CSV output path."""
    provided_path = output_path is not None
    provided_dir = output_dir is not None
    if provided_path and provided_dir:
        raise YahooIngestionError("Provide either --output or --output-dir, not both.")

    if provided_path:
        resolved = Path(output_path)
    elif provided_dir:
        resolved = Path(output_dir) / f"{ticker}_{resolved_expiration}_yahoo.csv"
    else:
        resolved = _default_output_path(ticker, resolved_expiration)

    if resolved.suffix.lower() != ".csv":
        raise YahooIngestionError(f"Normalized output path must end in .csv: {resolved}")
    return resolved


def _resolve_raw_cache_path(
    *,
    ticker: str,
    resolved_expiration: str,
    cache_dir: str | Path | None,
) -> Path:
    """Resolve the raw cache path used for cached payloads."""
    root = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_ROOT / ticker
    return root / f"{ticker}_{resolved_expiration}_yahoo.raw.json"


def _ensure_parent(path: Path) -> None:
    """Create the parent directory for one file path."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _serialize_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a dataframe into JSON-safe row records."""
    if frame is None or frame.empty:
        return []
    serialized = frame.copy()
    for column in serialized.columns:
        if pd.api.types.is_datetime64_any_dtype(serialized[column]):
            serialized[column] = serialized[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return serialized.to_dict(orient="records")


def _deserialize_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert cached row records back into a dataframe."""
    if not records:
        return pd.DataFrame()
    return pd.DataFrame.from_records(records)


def _safe_underlying_price(ticker_obj: Any) -> float:
    """Get one numeric underlying close reference plus its observed timestamp."""
    history = ticker_obj.history(period="1d")
    if history is None or history.empty or "Close" not in history.columns:
        raise YahooIngestionError(
            "Yahoo returned no usable underlying price history for the requested ticker."
        )

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        raise YahooIngestionError(
            "Yahoo returned no usable underlying price history for the requested ticker."
        )

    price = float(close.iloc[-1])
    if not math.isfinite(price):
        raise YahooIngestionError(
            "Yahoo returned no usable underlying price history for the requested ticker."
        )
    observed_at = pd.to_datetime(history.index[-1], errors="coerce", utc=True)
    if pd.isna(observed_at):
        observed_at_str = ""
    else:
        observed_at_str = observed_at.tz_convert(None).isoformat() + "Z"
    return price, observed_at_str


def _validate_raw_columns(frame: pd.DataFrame, side: str) -> None:
    """Fail clearly when a non-empty side is missing required Yahoo fields."""
    if frame is None or frame.empty:
        return

    missing = [column for column in RAW_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise YahooIngestionError(
            f"Yahoo option chain for {side} is missing required columns: {joined}"
        )


def _normalize_side(
    frame: pd.DataFrame,
    *,
    ticker: str,
    expiration: str,
    option_type: str,
    underlying_price: float,
    quote_observed_at: str,
    underlying_price_observed_at: str,
    underlying_price_source: str,
) -> pd.DataFrame:
    """Normalize one Yahoo option side into the canonical OptionQuoteRow contract."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(OPTION_QUOTE_REQUIRED_COLUMNS))

    _validate_raw_columns(frame, option_type)
    normalized = pd.DataFrame(
        {
            "ticker": ticker,
            "expiration": expiration,
            "strike": frame["strike"],
            "type": option_type,
            "bid": frame["bid"],
            "ask": frame["ask"],
            "mid": (pd.to_numeric(frame["bid"], errors="coerce") + pd.to_numeric(frame["ask"], errors="coerce"))
            / 2.0,
            "implied_vol": frame["impliedVolatility"],
            "underlying_price": underlying_price,
            "quote_observed_at": quote_observed_at,
            "underlying_price_observed_at": underlying_price_observed_at,
            "underlying_price_source": underlying_price_source,
        }
    )
    return validate_option_quote_frame(normalized)


def _normalize_payload(payload: dict[str, Any]) -> pd.DataFrame:
    """Normalize a cached or live payload into the canonical CSV frame."""
    ticker = _normalize_ticker(payload["ticker"])
    resolved_expiration = _parse_expiration(payload["resolved_expiration"]).strftime("%Y-%m-%d")
    underlying_price = float(payload["underlying_price"])
    quote_observed_at = str(payload.get("quote_observed_at", payload.get("fetched_at_utc", "")))
    underlying_price_observed_at = str(
        payload.get("underlying_price_observed_at", payload.get("fetched_at_utc", ""))
    )
    underlying_price_source = str(payload.get("underlying_price_source", "history.close"))

    if not math.isfinite(underlying_price):
        raise YahooIngestionError("Underlying price is required and must be numeric.")

    calls = _deserialize_frame(payload.get("calls_records", []))
    puts = _deserialize_frame(payload.get("puts_records", []))
    if calls.empty and puts.empty:
        raise YahooIngestionError("Yahoo returned an empty option chain for the requested ticker.")

    normalized_calls = _normalize_side(
        calls,
        ticker=ticker,
        expiration=resolved_expiration,
        option_type="call",
        underlying_price=underlying_price,
        quote_observed_at=quote_observed_at,
        underlying_price_observed_at=underlying_price_observed_at,
        underlying_price_source=underlying_price_source,
    )
    normalized_puts = _normalize_side(
        puts,
        ticker=ticker,
        expiration=resolved_expiration,
        option_type="put",
        underlying_price=underlying_price,
        quote_observed_at=quote_observed_at,
        underlying_price_observed_at=underlying_price_observed_at,
        underlying_price_source=underlying_price_source,
    )
    combined = pd.concat([normalized_calls, normalized_puts], ignore_index=True)
    if combined.empty:
        raise YahooIngestionError("Yahoo returned an empty option chain for the requested ticker.")

    combined = combined.dropna(subset=["strike"]).sort_values(
        by=["expiration", "type", "strike"], kind="stable"
    )
    return validate_option_quote_frame(combined).reset_index(drop=True)


def _build_payload(
    *,
    ticker: str,
    requested_expiration: str,
    resolved_expiration: str,
    underlying_price: float,
    quote_observed_at: str,
    underlying_price_observed_at: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    fetched_at: datetime,
) -> dict[str, Any]:
    """Build the raw payload record used for metadata and optional caching."""
    return {
        "source_vendor": "yahoo_finance",
        "source_library": "yfinance",
        "ticker": ticker,
        "requested_expiration": requested_expiration,
        "resolved_expiration": resolved_expiration,
        "fetched_at_utc": fetched_at.isoformat().replace("+00:00", "Z"),
        "quote_observed_at": quote_observed_at,
        "underlying_price": underlying_price,
        "underlying_price_observed_at": underlying_price_observed_at,
        "underlying_price_source": "history.close",
        "calls_columns": list(calls.columns),
        "puts_columns": list(puts.columns),
        "calls_records": _serialize_frame(calls),
        "puts_records": _serialize_frame(puts),
    }


def _cache_is_fresh(raw_cache_path: Path, cache_ttl_seconds: int, now: datetime) -> bool:
    """Return whether one raw cache file is still fresh."""
    if not raw_cache_path.exists():
        return False
    age_seconds = max(0.0, now.timestamp() - raw_cache_path.stat().st_mtime)
    return age_seconds <= float(cache_ttl_seconds)


def _read_cached_payload(raw_cache_path: Path) -> dict[str, Any]:
    """Load a cached raw payload."""
    with raw_cache_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    _ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _fetch_live_payload(
    *,
    ticker: str,
    requested_expiration: str,
    yf_module: Any,
    now: datetime,
) -> dict[str, Any]:
    """Fetch one live payload from Yahoo through yfinance."""
    ticker_obj = yf_module.Ticker(ticker)
    available_expirations = list(ticker_obj.options or [])
    resolved_expiration = _resolve_expiration(available_expirations, requested_expiration)
    chain = ticker_obj.option_chain(resolved_expiration)
    calls = getattr(chain, "calls", pd.DataFrame())
    puts = getattr(chain, "puts", pd.DataFrame())
    if (calls is None or calls.empty) and (puts is None or puts.empty):
        raise YahooIngestionError("Yahoo returned an empty option chain for the requested ticker.")

    underlying_price, underlying_price_observed_at = _safe_underlying_price(ticker_obj)
    return _build_payload(
        ticker=ticker,
        requested_expiration=requested_expiration,
        resolved_expiration=resolved_expiration,
        underlying_price=underlying_price,
        quote_observed_at=now.isoformat().replace("+00:00", "Z"),
        underlying_price_observed_at=underlying_price_observed_at,
        calls=calls if calls is not None else pd.DataFrame(),
        puts=puts if puts is not None else pd.DataFrame(),
        fetched_at=now,
    )


def ingest_yahoo_option_chain(
    *,
    ticker: str,
    requested_expiration: str,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    overwrite: bool = False,
    use_cache: bool = False,
    cache_ttl_seconds: int = 3600,
    write_raw_json: bool = False,
    yf_module: Any | None = None,
    now: datetime | None = None,
) -> YahooIngestionResult:
    """Fetch, normalize, and persist one Yahoo option-chain snapshot."""
    current_time = now or _utc_now()
    normalized_ticker = _normalize_ticker(ticker)
    if cache_ttl_seconds < 0:
        raise YahooIngestionError("cache_ttl_seconds must be non-negative.")

    active_yf_module = yf_module or _import_yfinance()

    raw_cache_path: Path | None = None
    cache_hit = False
    payload: dict[str, Any]

    if use_cache:
        available_expirations = list(active_yf_module.Ticker(normalized_ticker).options or [])
        resolved_expiration = _resolve_expiration(available_expirations, requested_expiration)
        raw_cache_path = _resolve_raw_cache_path(
            ticker=normalized_ticker,
            resolved_expiration=resolved_expiration,
            cache_dir=cache_dir,
        )
        if _cache_is_fresh(raw_cache_path, cache_ttl_seconds, current_time):
            payload = _read_cached_payload(raw_cache_path)
            cache_hit = True
        else:
            payload = _fetch_live_payload(
                ticker=normalized_ticker,
                requested_expiration=requested_expiration,
                yf_module=active_yf_module,
                now=current_time,
            )
    else:
        payload = _fetch_live_payload(
            ticker=normalized_ticker,
            requested_expiration=requested_expiration,
            yf_module=active_yf_module,
            now=current_time,
        )

    resolved_expiration = payload["resolved_expiration"]
    output_csv_path = _resolve_output_path(
        ticker=normalized_ticker,
        resolved_expiration=resolved_expiration,
        output_path=output_path,
        output_dir=output_dir,
    )
    metadata_path = output_csv_path.with_suffix(output_csv_path.suffix + ".meta.json")
    if output_csv_path.exists() and not overwrite:
        raise YahooIngestionError(
            f"Normalized output file already exists. Re-run with --overwrite to replace it: {output_csv_path}"
        )

    normalized = _normalize_payload(payload)
    _ensure_parent(output_csv_path)
    normalized.to_csv(output_csv_path, index=False)

    raw_payload_written = False
    if raw_cache_path is None and (write_raw_json or cache_dir is not None):
        raw_cache_path = _resolve_raw_cache_path(
            ticker=normalized_ticker,
            resolved_expiration=resolved_expiration,
            cache_dir=cache_dir,
        )
    if raw_cache_path is not None and (write_raw_json or use_cache or cache_dir is not None):
        _write_json(raw_cache_path, payload)
        raw_payload_written = True

    metadata = {
        "snapshot_id": _build_snapshot_id(
            normalized_ticker,
            resolved_expiration,
            payload["quote_observed_at"],
        ),
        "snapshot_source": payload["source_vendor"],
        "source_vendor": payload["source_vendor"],
        "source_library": payload["source_library"],
        "source_library_version": getattr(active_yf_module, "__version__", "unknown"),
        "ticker_requested": str(ticker).strip(),
        "ticker_normalized": normalized_ticker,
        "expiration_requested": requested_expiration,
        "expiration_resolved": resolved_expiration,
        "expiration_start": resolved_expiration,
        "expiration_end": resolved_expiration,
        "fetched_at_utc": payload["fetched_at_utc"],
        "quote_observed_at": payload["quote_observed_at"],
        "underlying_price": payload["underlying_price"],
        "underlying_price_observed_at": payload.get(
            "underlying_price_observed_at",
            payload["fetched_at_utc"],
        ),
        "underlying_price_source": payload["underlying_price_source"],
        "calls_row_count": len(payload.get("calls_records", [])),
        "puts_row_count": len(payload.get("puts_records", [])),
        "normalized_row_count": int(len(normalized)),
        "output_csv_path": str(output_csv_path),
        "raw_cache_path": str(raw_cache_path) if raw_cache_path is not None else "",
        "raw_payload_written": raw_payload_written,
        "cache_hit": cache_hit,
        "cache_ttl_seconds": cache_ttl_seconds,
        "command_version": INGESTION_VERSION,
    }
    _write_json(metadata_path, metadata)
    return YahooIngestionResult(csv_path=output_csv_path, metadata_path=metadata_path, metadata=metadata)


def build_cli_summary(result: YahooIngestionResult) -> str:
    """Return a concise CLI completion summary."""
    metadata = result.metadata
    return (
        "Optional Yahoo ingestion complete. "
        f"Offline scanner input written to: {result.csv_path} "
        f"(resolved_expiration={metadata['expiration_resolved']}, "
        f"row_count={metadata['normalized_row_count']}, cache_hit={metadata['cache_hit']})"
    )


def _build_fake_chain(calls: pd.DataFrame, puts: pd.DataFrame) -> Any:
    """Build a simple option-chain-like object for tests if needed."""
    return SimpleNamespace(calls=calls, puts=puts)
