from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.calibration import (
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    SPY_EXPIRATION_CLOSE_POLICY,
    build_required_outcome_key,
    market_close_timestamp_for_event_date,
)
from options_edge_scanner.data import (
    AlpacaAcquisitionError,
    AlpacaCredentials,
    AlpacaStockBarsRequest,
    build_realized_underlying_artifact_id,
    build_realized_underlying_observation_id,
    load_alpaca_credentials_from_env,
    normalize_alpaca_stock_bars_to_realized_underlying,
    validate_realized_underlying_frame,
)
from options_edge_scanner.data.alpaca_historical import acquire_alpaca_realized_underlying


def _make_realized_underlying_row(
    *,
    event_date: str = "2026-06-15",
    observed_price: float = 741.25,
    adjustment_mode: str = "raw",
    acquired_at: str | None = None,
) -> dict[str, object]:
    resolved_acquired_at = acquired_at or (
        (pd.Timestamp(event_date).tz_localize("UTC") + pd.Timedelta(days=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    artifact_id = build_realized_underlying_artifact_id(
        source="alpaca",
        ticker="SPY",
        start=event_date,
        end=event_date,
        timeframe="1Day",
        adjustment_mode=adjustment_mode,
        source_feed="sip",
        terminal_price_convention=SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention,
    )
    required_outcome_key = build_required_outcome_key(
        ticker="SPY",
        expiration=event_date,
        required_outcome_horizon="expiration",
        realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    )
    observation_id = build_realized_underlying_observation_id(
        ticker="SPY",
        event_date=event_date,
        required_outcome_horizon="expiration",
        realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
        terminal_price_convention=SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention,
        terminal_price_convention_version=SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention_version,
        source="alpaca",
        source_dataset="stocks.bars.v2",
        source_feed="sip",
        timeframe="1Day",
        adjustment_mode=adjustment_mode,
    )
    market_close = market_close_timestamp_for_event_date(
        event_date,
        policy=SPY_EXPIRATION_CLOSE_POLICY,
    )
    return {
        "observation_id": observation_id,
        "required_outcome_key": required_outcome_key,
        "ticker": "SPY",
        "event_date": event_date,
        "required_outcome_horizon": "expiration",
        "realized_outcome_measure": TERMINAL_UNDERLYING_OUTCOME_MEASURE,
        "terminal_price_convention": SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention,
        "terminal_price_convention_version": SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention_version,
        "observed_price": observed_price,
        "observed_at": market_close,
        "market_close_timestamp": market_close,
        "price_field": SPY_EXPIRATION_CLOSE_POLICY.price_field,
        "observed_market_session": SPY_EXPIRATION_CLOSE_POLICY.observed_market_session,
        "source": "alpaca",
        "source_dataset": "stocks.bars.v2",
        "source_feed": "sip",
        "timeframe": "1Day",
        "adjustment_mode": adjustment_mode,
        "acquired_at": resolved_acquired_at,
        "provenance_artifact_id": artifact_id,
        "source_bar_timestamp": f"{event_date}T04:00:00Z",
        "provider_symbol": "SPY",
        "currency": "USD",
    }


def test_realized_underlying_contract_validates_one_normalized_spy_row() -> None:
    frame = pd.DataFrame([_make_realized_underlying_row()])

    validated = validate_realized_underlying_frame(frame)

    assert len(validated) == 1
    assert validated.loc[0, "ticker"] == "SPY"
    assert validated.loc[0, "required_outcome_horizon"] == "expiration"
    assert validated.loc[0, "realized_outcome_measure"] == "terminal_underlying_price"
    assert validated.loc[0, "observed_at"].strftime("%Y-%m-%dT%H:%M:%S") == "2026-06-15T20:00:00"


def test_realized_underlying_contract_preserves_explicit_adjustment_mode_provenance() -> None:
    raw_row = _make_realized_underlying_row(adjustment_mode="raw")
    adjusted_row = _make_realized_underlying_row(
        event_date="2026-07-17",
        adjustment_mode="dividend",
    )
    validated = validate_realized_underlying_frame(pd.DataFrame([raw_row, adjusted_row]))

    assert validated["adjustment_mode"].tolist() == ["raw", "dividend"]
    assert validated["provenance_artifact_id"].nunique() == 2


def test_realized_underlying_contract_rejects_duplicate_required_outcome_keys() -> None:
    rows = [
        _make_realized_underlying_row(),
        _make_realized_underlying_row(adjustment_mode="dividend"),
    ]

    with pytest.raises(
        ValueError,
        match="required_outcome_key values must be unique in realized underlying observations",
    ):
        validate_realized_underlying_frame(pd.DataFrame(rows))


def test_realized_underlying_contract_rejects_outcome_timestamp_before_market_close() -> None:
    row = _make_realized_underlying_row()
    row["observed_at"] = "2026-06-15T19:59:00Z"

    with pytest.raises(
        ValueError,
        match="observed_at must equal market_close_timestamp",
    ):
        validate_realized_underlying_frame(pd.DataFrame([row]))


def test_normalize_alpaca_stock_bars_to_realized_underlying_maps_daily_bars_into_contract() -> None:
    request = AlpacaStockBarsRequest(
        ticker="SPY",
        start="2026-06-15",
        end="2026-07-17",
        timeframe="1Day",
        adjustment="raw",
        feed="sip",
        required_outcome_horizon="expiration",
    )
    pages = [
        {
            "bars": {
                "SPY": [
                    {"t": "2026-06-15T04:00:00Z", "c": 741.25},
                    {"t": "2026-07-17T04:00:00Z", "c": 745.50},
                ]
            },
            "next_page_token": None,
        }
    ]

    normalized = normalize_alpaca_stock_bars_to_realized_underlying(
        request,
        pages=pages,
        acquired_at="2026-08-17T12:00:00Z",
    )

    assert normalized["event_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-06-15", "2026-07-17"]
    assert normalized["observed_price"].tolist() == [741.25, 745.50]
    assert normalized["adjustment_mode"].tolist() == ["raw", "raw"]
    assert normalized["source_feed"].tolist() == ["sip", "sip"]


def test_normalize_alpaca_stock_bars_is_deterministic_for_same_pages() -> None:
    request = AlpacaStockBarsRequest(ticker="SPY", start="2026-06-15", end="2026-06-15")
    pages = [{"bars": {"SPY": [{"t": "2026-06-15T04:00:00Z", "c": 741.25}]}, "next_page_token": None}]

    first = normalize_alpaca_stock_bars_to_realized_underlying(
        request,
        pages=pages,
        acquired_at="2026-08-17T12:00:00Z",
    )
    second = normalize_alpaca_stock_bars_to_realized_underlying(
        request,
        pages=pages,
        acquired_at="2026-08-17T12:00:00Z",
    )

    assert first.equals(second)


def test_acquire_alpaca_realized_underlying_generates_acquired_at_when_omitted() -> None:
    request = AlpacaStockBarsRequest(ticker="SPY", start="2026-06-15", end="2026-06-15")

    def _http_get_json(_url: str, *, headers: dict[str, str]) -> dict[str, object]:
        _ = headers
        return {
            "bars": {"SPY": [{"t": "2026-06-15T04:00:00Z", "c": 741.25}]},
            "next_page_token": None,
        }

    acquisition = acquire_alpaca_realized_underlying(
        request,
        credentials=AlpacaCredentials(api_key_id="key", api_secret_key="secret"),
        http_get_json=_http_get_json,
    )

    assert len(acquisition.observations) == 1
    assert acquisition.observations.loc[0, "acquired_at"] >= acquisition.observations.loc[0, "observed_at"]


def test_load_alpaca_credentials_from_env_reads_supported_variable_names() -> None:
    credentials = load_alpaca_credentials_from_env(
        {
            "APCA_API_KEY_ID": "key-id",
            "APCA_API_SECRET_KEY": "secret-key",
        }
    )

    assert credentials.api_key_id == "key-id"
    assert credentials.api_secret_key == "secret-key"


def test_load_alpaca_credentials_from_env_rejects_missing_values() -> None:
    with pytest.raises(AlpacaAcquisitionError, match="Alpaca credentials are unavailable"):
        load_alpaca_credentials_from_env({})


def test_acquire_alpaca_realized_underlying_surfaces_provider_failures() -> None:
    request = AlpacaStockBarsRequest(ticker="SPY", start="2026-06-15", end="2026-06-15")

    def _failing_http_get_json(_url: str, *, headers: dict[str, str]) -> dict[str, object]:
        _ = headers
        raise AlpacaAcquisitionError("simulated provider outage")

    with pytest.raises(AlpacaAcquisitionError, match="simulated provider outage"):
        acquire_alpaca_realized_underlying(
            request,
            credentials=AlpacaCredentials(api_key_id="key", api_secret_key="secret"),
            http_get_json=_failing_http_get_json,
        )


def test_realized_underlying_contract_rejects_non_trading_day_event_dates() -> None:
    row = _make_realized_underlying_row()
    row["event_date"] = "2026-12-25"
    row["required_outcome_key"] = "SPY|2026-12-25|expiration|terminal_underlying_price"
    row["observation_id"] = build_realized_underlying_observation_id(
        ticker="SPY",
        event_date="2026-12-25",
        required_outcome_horizon="expiration",
        realized_outcome_measure="terminal_underlying_price",
        terminal_price_convention=SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention,
        terminal_price_convention_version=SPY_EXPIRATION_CLOSE_POLICY.terminal_price_convention_version,
        source="alpaca",
        source_dataset="stocks.bars.v2",
        source_feed="sip",
        timeframe="1Day",
        adjustment_mode="raw",
    )
    row["market_close_timestamp"] = "2026-12-25T21:00:00Z"
    row["observed_at"] = "2026-12-25T21:00:00Z"
    row["acquired_at"] = "2026-12-26T00:00:00Z"
    row["source_bar_timestamp"] = "2026-12-25T05:00:00Z"

    with pytest.raises(ValueError, match="not a regular US equity trading day"):
        validate_realized_underlying_frame(pd.DataFrame([row]))


def test_realized_underlying_contract_accepts_2026_06_18_holiday_adjusted_thursday_expiration() -> None:
    frame = pd.DataFrame([_make_realized_underlying_row(event_date="2026-06-18")])

    validated = validate_realized_underlying_frame(frame)

    assert len(validated) == 1
    assert validated.loc[0, "event_date"].strftime("%Y-%m-%d") == "2026-06-18"
    assert validated.loc[0, "observed_at"].strftime("%Y-%m-%dT%H:%M:%S") == "2026-06-18T20:00:00"
