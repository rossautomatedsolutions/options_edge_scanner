"""Alpaca historical stock-bar acquisition for realized underlying observations."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from options_edge_scanner.calibration.contracts import (
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    build_required_outcome_key,
    format_date_like,
    format_utc_timestamp,
)
from options_edge_scanner.calibration.terminal_semantics import (
    market_close_timestamp_for_event_date,
    resolve_terminal_observation_policy,
)
from options_edge_scanner.data.realized_underlying import (
    build_realized_underlying_artifact_id,
    build_realized_underlying_observation_id,
    validate_realized_underlying_frame,
)


_ALPACA_STOCK_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
_ALPACA_SOURCE = "alpaca"
_ALPACA_SOURCE_DATASET = "stocks.bars.v2"
_ALPACA_ALLOWED_FEEDS = {"sip", "iex", "boats", "otc"}
_ALPACA_ALLOWED_SORTS = {"asc", "desc"}


class AlpacaAcquisitionError(RuntimeError):
    """Raised when Alpaca acquisition fails or returns unusable data."""


@dataclass(frozen=True)
class AlpacaCredentials:
    """Credential pair for authenticated Alpaca market-data requests."""

    api_key_id: str
    api_secret_key: str


@dataclass(frozen=True)
class AlpacaStockBarsRequest:
    """Explicit historical stock-bar request configuration."""

    ticker: str
    start: str
    end: str
    timeframe: str = "1Day"
    adjustment: str = "raw"
    feed: str = "sip"
    sort: str = "asc"
    limit: int = 1000
    required_outcome_horizon: str = "expiration"

    def normalized_ticker(self) -> str:
        """Return the normalized ticker symbol."""
        return str(self.ticker).strip().upper()


@dataclass(frozen=True)
class AlpacaRealizedUnderlyingAcquisition:
    """Normalized realized underlying observations plus acquisition metadata."""

    observations: pd.DataFrame
    metadata: dict[str, Any]
    raw_pages: list[dict[str, Any]]


def load_alpaca_credentials_from_env(env: dict[str, str] | None = None) -> AlpacaCredentials:
    """Load Alpaca credentials from conventional environment variables."""
    environment = env if env is not None else os.environ
    api_key_id = (
        environment.get("APCA_API_KEY_ID")
        or environment.get("ALPACA_API_KEY_ID")
        or ""
    ).strip()
    api_secret_key = (
        environment.get("APCA_API_SECRET_KEY")
        or environment.get("ALPACA_API_SECRET_KEY")
        or ""
    ).strip()

    if not api_key_id or not api_secret_key:
        raise AlpacaAcquisitionError(
            "Alpaca credentials are unavailable. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY "
            "or the ALPACA_* equivalents before running historical realized-underlying acquisition."
        )
    return AlpacaCredentials(api_key_id=api_key_id, api_secret_key=api_secret_key)


def _validate_request(request: AlpacaStockBarsRequest) -> AlpacaStockBarsRequest:
    """Validate one explicit Alpaca historical-bars request."""
    ticker = request.normalized_ticker()
    if not ticker:
        raise ValueError("ticker must be present and non-empty.")
    if str(request.feed).strip() not in _ALPACA_ALLOWED_FEEDS:
        allowed = ", ".join(sorted(_ALPACA_ALLOWED_FEEDS))
        raise ValueError(f"feed must be one of: {allowed}")
    if str(request.sort).strip() not in _ALPACA_ALLOWED_SORTS:
        allowed = ", ".join(sorted(_ALPACA_ALLOWED_SORTS))
        raise ValueError(f"sort must be one of: {allowed}")
    if int(request.limit) <= 0 or int(request.limit) > 10000:
        raise ValueError("limit must be between 1 and 10000.")

    start = pd.to_datetime(request.start, errors="coerce", utc=True)
    end = pd.to_datetime(request.end, errors="coerce", utc=True)
    if pd.isna(start) or pd.isna(end):
        raise ValueError("start and end must be valid date-like values.")
    if start > end:
        raise ValueError("start must be on or before end.")

    return AlpacaStockBarsRequest(
        ticker=ticker,
        start=format_date_like(start),
        end=format_date_like(end),
        timeframe=str(request.timeframe).strip(),
        adjustment=str(request.adjustment).strip(),
        feed=str(request.feed).strip(),
        sort=str(request.sort).strip(),
        limit=int(request.limit),
        required_outcome_horizon=str(request.required_outcome_horizon).strip(),
    )


def _default_http_get_json(url: str, *, headers: dict[str, str]) -> dict[str, Any]:
    """Perform one authenticated JSON GET request."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AlpacaAcquisitionError(
            f"Alpaca historical bars request failed with HTTP {exc.code}: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AlpacaAcquisitionError(f"Alpaca network failure: {exc.reason}") from exc

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AlpacaAcquisitionError("Alpaca returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise AlpacaAcquisitionError("Alpaca returned a non-object JSON payload.")
    return decoded


def _build_request_url(
    request: AlpacaStockBarsRequest,
    *,
    page_token: str | None = None,
) -> str:
    """Build one deterministic Alpaca historical-bars URL."""
    params = [
        ("symbols", request.normalized_ticker()),
        ("timeframe", request.timeframe),
        ("start", request.start),
        ("end", request.end),
        ("limit", str(request.limit)),
        ("adjustment", request.adjustment),
        ("feed", request.feed),
        ("sort", request.sort),
    ]
    if page_token is not None:
        params.append(("page_token", page_token))
    return _ALPACA_STOCK_BARS_URL + "?" + urllib.parse.urlencode(params)


def fetch_alpaca_stock_bars_pages(
    request: AlpacaStockBarsRequest,
    *,
    credentials: AlpacaCredentials,
    http_get_json: Callable[..., dict[str, Any]] = _default_http_get_json,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch every page for one Alpaca historical stock-bars request."""
    validated_request = _validate_request(request)
    headers = {
        "APCA-API-KEY-ID": credentials.api_key_id,
        "APCA-API-SECRET-KEY": credentials.api_secret_key,
    }

    pages: list[dict[str, Any]] = []
    request_urls: list[str] = []
    page_token: str | None = None

    while True:
        url = _build_request_url(validated_request, page_token=page_token)
        request_urls.append(url)
        payload = http_get_json(url, headers=headers)
        pages.append(payload)

        next_page_token = payload.get("next_page_token")
        if next_page_token is None:
            break
        if not isinstance(next_page_token, str) or not next_page_token.strip():
            raise AlpacaAcquisitionError("Alpaca returned an invalid next_page_token.")
        page_token = next_page_token.strip()

    return pages, request_urls


def _extract_symbol_bars(
    pages: list[dict[str, Any]],
    *,
    ticker: str,
) -> list[dict[str, Any]]:
    """Return one flattened list of bar payloads for the requested symbol."""
    bars: list[dict[str, Any]] = []
    for page in pages:
        page_bars = page.get("bars")
        if not isinstance(page_bars, dict):
            raise AlpacaAcquisitionError("Alpaca payload is missing the bars object.")

        symbol_bars = page_bars.get(ticker, [])
        if symbol_bars is None:
            symbol_bars = []
        if not isinstance(symbol_bars, list):
            raise AlpacaAcquisitionError("Alpaca returned a non-list bars payload for the symbol.")
        for bar in symbol_bars:
            if not isinstance(bar, dict):
                raise AlpacaAcquisitionError("Alpaca returned a malformed bar payload.")
            bars.append(bar)
    return bars


def _event_date_from_bar_timestamp(timestamp_value: object) -> str:
    """Map one raw Alpaca bar timestamp into the local event date."""
    parsed = pd.to_datetime(timestamp_value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise AlpacaAcquisitionError(f"Alpaca bar timestamp is invalid: {timestamp_value}")
    eastern = pd.Timestamp(parsed).tz_convert("America/New_York")
    return eastern.strftime("%Y-%m-%d")


def normalize_alpaca_stock_bars_to_realized_underlying(
    request: AlpacaStockBarsRequest,
    *,
    pages: list[dict[str, Any]],
    acquired_at: object | None = None,
    provenance_artifact_id: str | None = None,
) -> pd.DataFrame:
    """Normalize fetched Alpaca stock bars into the provider-neutral contract."""
    validated_request = _validate_request(request)
    ticker = validated_request.normalized_ticker()
    policy = resolve_terminal_observation_policy(
        ticker=ticker,
        required_outcome_horizon=validated_request.required_outcome_horizon,
    )
    bars = _extract_symbol_bars(pages, ticker=ticker)
    if not bars:
        raise AlpacaAcquisitionError(
            f"Alpaca returned no bars for ticker={ticker}, start={validated_request.start}, "
            f"end={validated_request.end}, timeframe={validated_request.timeframe}, "
            f"feed={validated_request.feed}, adjustment={validated_request.adjustment}."
        )

    artifact_id = provenance_artifact_id or build_realized_underlying_artifact_id(
        source=_ALPACA_SOURCE,
        ticker=ticker,
        start=validated_request.start,
        end=validated_request.end,
        timeframe=validated_request.timeframe,
        adjustment_mode=validated_request.adjustment,
        source_feed=validated_request.feed,
        terminal_price_convention=policy.terminal_price_convention,
    )
    acquired_at_value = format_utc_timestamp(
        acquired_at if acquired_at is not None else pd.Timestamp.now(tz="UTC")
    )

    records: list[dict[str, Any]] = []
    for bar in bars:
        if "t" not in bar or "c" not in bar:
            raise AlpacaAcquisitionError("Alpaca bar payload must include t and c fields.")

        event_date = _event_date_from_bar_timestamp(bar["t"])
        required_outcome_key = build_required_outcome_key(
            ticker=ticker,
            expiration=event_date,
            required_outcome_horizon=validated_request.required_outcome_horizon,
            realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
        )
        observation_id = build_realized_underlying_observation_id(
            ticker=ticker,
            event_date=event_date,
            required_outcome_horizon=validated_request.required_outcome_horizon,
            realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
            terminal_price_convention=policy.terminal_price_convention,
            terminal_price_convention_version=policy.terminal_price_convention_version,
            source=_ALPACA_SOURCE,
            source_dataset=_ALPACA_SOURCE_DATASET,
            source_feed=validated_request.feed,
            timeframe=validated_request.timeframe,
            adjustment_mode=validated_request.adjustment,
        )
        market_close_timestamp = market_close_timestamp_for_event_date(
            event_date,
            policy=policy,
        )

        records.append(
            {
                "observation_id": observation_id,
                "required_outcome_key": required_outcome_key,
                "ticker": ticker,
                "event_date": event_date,
                "required_outcome_horizon": validated_request.required_outcome_horizon,
                "realized_outcome_measure": TERMINAL_UNDERLYING_OUTCOME_MEASURE,
                "terminal_price_convention": policy.terminal_price_convention,
                "terminal_price_convention_version": policy.terminal_price_convention_version,
                "observed_price": float(bar["c"]),
                "observed_at": market_close_timestamp,
                "market_close_timestamp": market_close_timestamp,
                "price_field": policy.price_field,
                "observed_market_session": policy.observed_market_session,
                "source": _ALPACA_SOURCE,
                "source_dataset": _ALPACA_SOURCE_DATASET,
                "source_feed": validated_request.feed,
                "timeframe": validated_request.timeframe,
                "adjustment_mode": validated_request.adjustment,
                "acquired_at": acquired_at_value,
                "provenance_artifact_id": artifact_id,
                "source_bar_timestamp": format_utc_timestamp(bar["t"]),
                "provider_symbol": ticker,
                "currency": "USD",
            }
        )

    return validate_realized_underlying_frame(pd.DataFrame.from_records(records))


def acquire_alpaca_realized_underlying(
    request: AlpacaStockBarsRequest,
    *,
    credentials: AlpacaCredentials | None = None,
    http_get_json: Callable[..., dict[str, Any]] = _default_http_get_json,
    acquired_at: object | None = None,
) -> AlpacaRealizedUnderlyingAcquisition:
    """Fetch and normalize one realized underlying artifact from Alpaca."""
    validated_request = _validate_request(request)
    resolved_credentials = credentials or load_alpaca_credentials_from_env()
    pages, request_urls = fetch_alpaca_stock_bars_pages(
        validated_request,
        credentials=resolved_credentials,
        http_get_json=http_get_json,
    )
    observations = normalize_alpaca_stock_bars_to_realized_underlying(
        validated_request,
        pages=pages,
        acquired_at=acquired_at,
    )
    policy = resolve_terminal_observation_policy(
        ticker=validated_request.normalized_ticker(),
        required_outcome_horizon=validated_request.required_outcome_horizon,
    )
    metadata = {
        "artifact_id": observations.iloc[0]["provenance_artifact_id"],
        "ticker": validated_request.normalized_ticker(),
        "requested_start": validated_request.start,
        "requested_end": validated_request.end,
        "timeframe": validated_request.timeframe,
        "adjustment_mode": validated_request.adjustment,
        "source_feed": validated_request.feed,
        "sort": validated_request.sort,
        "limit": validated_request.limit,
        "required_outcome_horizon": validated_request.required_outcome_horizon,
        "row_count": int(len(observations)),
        "page_count": len(pages),
        "acquired_at": observations.iloc[0]["acquired_at"],
        "source": _ALPACA_SOURCE,
        "source_dataset": _ALPACA_SOURCE_DATASET,
        "provider_endpoint": _ALPACA_STOCK_BARS_URL,
        "request_urls": request_urls,
        "terminal_observation_policy": policy.to_metadata(),
    }
    return AlpacaRealizedUnderlyingAcquisition(
        observations=observations,
        metadata=metadata,
        raw_pages=pages,
    )
