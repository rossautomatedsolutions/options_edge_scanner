from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.calibration.materialization import (
    collect_required_outcome_requests_from_manifest,
    materialize_realized_outcomes,
    materialize_realized_outcomes_from_snapshot_manifest,
)
from options_edge_scanner.cli.materialize_realized_outcomes import main
from options_edge_scanner.data.realized_underlying import (
    build_realized_underlying_artifact_id,
    build_realized_underlying_observation_id,
)
from options_edge_scanner.data.realized_underlying import write_realized_underlying_frame


OPTION_CHAIN_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def _write_strict_snapshot(
    root: Path,
    *,
    snapshot_id: str,
    expiration: str,
    quote_observed_at: str,
    as_of: str,
    underlying_price: float = 741.75,
) -> tuple[Path, Path]:
    snapshot_dir = root / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    quotes = pd.read_csv(OPTION_CHAIN_FIXTURE_PATH)
    quotes["ticker"] = "SPY"
    quotes["expiration"] = expiration
    quotes["quote_observed_at"] = quote_observed_at
    quotes["underlying_price"] = underlying_price
    quotes["underlying_price_observed_at"] = quote_observed_at
    quotes["underlying_price_source"] = "fixture.snapshot"
    quotes["snapshot_id"] = snapshot_id

    chain_path = snapshot_dir / f"{snapshot_id}.csv"
    quotes.to_csv(chain_path, index=False)

    metadata = {
        "snapshot_id": snapshot_id,
        "snapshot_source": "fixture.vendor",
        "source_vendor": "fixture.vendor",
        "ticker_normalized": "SPY",
        "quote_observed_at": quote_observed_at,
        "underlying_price": underlying_price,
        "underlying_price_observed_at": quote_observed_at,
        "underlying_price_source": "fixture.snapshot",
        "expiration_start": expiration,
        "expiration_end": expiration,
    }
    metadata_path = chain_path.with_suffix(chain_path.suffix + ".meta.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return chain_path, metadata_path


def _write_manifest(
    root: Path,
    rows: list[dict[str, object]],
) -> Path:
    manifest_path = root / "historical_manifest.csv"
    pd.DataFrame(rows).to_csv(manifest_path, index=False)
    return manifest_path


def _realized_underlying_row(
    *,
    event_date: str,
    observed_price: float,
) -> dict[str, object]:
    artifact_id = build_realized_underlying_artifact_id(
        source="alpaca",
        ticker="SPY",
        start=event_date,
        end=event_date,
        timeframe="1Day",
        adjustment_mode="raw",
        source_feed="sip",
        terminal_price_convention="spy_expiration_day_close_proxy",
    )
    observation_id = build_realized_underlying_observation_id(
        ticker="SPY",
        event_date=event_date,
        required_outcome_horizon="expiration",
        realized_outcome_measure="terminal_underlying_price",
        terminal_price_convention="spy_expiration_day_close_proxy",
        terminal_price_convention_version="1",
        source="alpaca",
        source_dataset="stocks.bars.v2",
        source_feed="sip",
        timeframe="1Day",
        adjustment_mode="raw",
    )
    return {
        "observation_id": observation_id,
        "required_outcome_key": f"SPY|{event_date}|expiration|terminal_underlying_price",
        "ticker": "SPY",
        "event_date": event_date,
        "required_outcome_horizon": "expiration",
        "realized_outcome_measure": "terminal_underlying_price",
        "terminal_price_convention": "spy_expiration_day_close_proxy",
        "terminal_price_convention_version": "1",
        "observed_price": observed_price,
        "observed_at": f"{event_date}T20:00:00Z",
        "market_close_timestamp": f"{event_date}T20:00:00Z",
        "price_field": "close",
        "observed_market_session": "regular_close",
        "source": "alpaca",
        "source_dataset": "stocks.bars.v2",
        "source_feed": "sip",
        "timeframe": "1Day",
        "adjustment_mode": "raw",
        "acquired_at": "2026-08-17T12:00:00Z",
        "provenance_artifact_id": artifact_id,
        "source_bar_timestamp": f"{event_date}T04:00:00Z",
        "provider_symbol": "SPY",
        "currency": "USD",
    }


def test_materialize_realized_outcomes_from_strict_snapshot_manifest(tmp_path: Path) -> None:
    chain_a, metadata_a = _write_strict_snapshot(
        tmp_path,
        snapshot_id="spy-20260613-185808",
        expiration="2026-06-15",
        quote_observed_at="2026-06-13T18:58:08Z",
        as_of="2026-06-13",
    )
    chain_b, metadata_b = _write_strict_snapshot(
        tmp_path,
        snapshot_id="spy-20260614-125531",
        expiration="2026-07-17",
        quote_observed_at="2026-06-14T12:55:31Z",
        as_of="2026-06-14",
    )
    manifest_path = _write_manifest(
        tmp_path,
        [
            {
                "snapshot_id": "spy-20260613-185808",
                "ticker": "SPY",
                "as_of": "2026-06-13",
                "chain_path": str(chain_a),
                "metadata_path": str(metadata_a),
            },
            {
                "snapshot_id": "spy-20260614-125531",
                "ticker": "SPY",
                "as_of": "2026-06-14",
                "chain_path": str(chain_b),
                "metadata_path": str(metadata_b),
            },
        ],
    )
    realized_underlying_path = tmp_path / "realized_underlying.csv"
    write_realized_underlying_frame(
        pd.DataFrame(
            [
                _realized_underlying_row(event_date="2026-06-15", observed_price=741.25),
                _realized_underlying_row(event_date="2026-07-17", observed_price=745.50),
            ]
        ),
        realized_underlying_path,
    )

    artifacts = materialize_realized_outcomes_from_snapshot_manifest(
        manifest_path=manifest_path,
        realized_underlying_paths=[realized_underlying_path],
    )

    assert artifacts.required_observations["expiration"].tolist() == ["2026-06-15", "2026-07-17"]
    assert artifacts.outcomes["expiration"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-06-15",
        "2026-07-17",
    ]
    assert artifacts.outcomes["realized_terminal_underlying_price"].tolist() == [741.25, 745.50]
    assert artifacts.outcomes["source_snapshot_count"].tolist() == [1, 1]


def test_materialize_realized_outcomes_rejects_missing_terminal_observation(tmp_path: Path) -> None:
    chain_path, metadata_path = _write_strict_snapshot(
        tmp_path,
        snapshot_id="spy-20260613-185808",
        expiration="2026-06-15",
        quote_observed_at="2026-06-13T18:58:08Z",
        as_of="2026-06-13",
    )
    manifest_path = _write_manifest(
        tmp_path,
        [
            {
                "snapshot_id": "spy-20260613-185808",
                "ticker": "SPY",
                "as_of": "2026-06-13",
                "chain_path": str(chain_path),
                "metadata_path": str(metadata_path),
            }
        ],
    )
    requests = collect_required_outcome_requests_from_manifest(manifest_path)
    realized_underlying = pd.DataFrame(
        [_realized_underlying_row(event_date="2026-06-16", observed_price=742.0)]
    )

    with pytest.raises(
        ValueError,
        match="Exact ticker/event-date matching is required; no forward-fill or calendar-roll convention",
    ):
        materialize_realized_outcomes(
            required_observations=requests,
            realized_underlying=realized_underlying,
        )


def test_materialize_realized_outcomes_rejects_cross_symbol_pairing() -> None:
    requests = pd.DataFrame(
        [
            {
                "required_outcome_key": "SPY|2026-06-15|expiration|terminal_underlying_price",
                "ticker": "QQQ",
                "expiration": "2026-06-15",
                "required_outcome_horizon": "expiration",
                "realized_outcome_measure": "terminal_underlying_price",
                "terminal_price_convention": "spy_expiration_day_close_proxy",
                "terminal_price_convention_version": "1",
                "source_snapshot_count": 1,
                "source_snapshot_ids": "spy-snapshot",
            }
        ]
    )
    realized_underlying = pd.DataFrame(
        [_realized_underlying_row(event_date="2026-06-15", observed_price=741.25)]
    )

    with pytest.raises(ValueError, match="Ticker mismatch detected during outcome materialization"):
        materialize_realized_outcomes(
            required_observations=requests,
            realized_underlying=realized_underlying,
        )


def test_materialize_realized_outcomes_rejects_cross_date_pairing() -> None:
    requests = pd.DataFrame(
        [
            {
                "required_outcome_key": "SPY|2026-06-15|expiration|terminal_underlying_price",
                "ticker": "SPY",
                "expiration": "2026-06-16",
                "required_outcome_horizon": "expiration",
                "realized_outcome_measure": "terminal_underlying_price",
                "terminal_price_convention": "spy_expiration_day_close_proxy",
                "terminal_price_convention_version": "1",
                "source_snapshot_count": 1,
                "source_snapshot_ids": "spy-snapshot",
            }
        ]
    )
    realized_underlying = pd.DataFrame(
        [_realized_underlying_row(event_date="2026-06-15", observed_price=741.25)]
    )

    with pytest.raises(ValueError, match="Expiration/event_date mismatch detected during outcome materialization"):
        materialize_realized_outcomes(
            required_observations=requests,
            realized_underlying=realized_underlying,
        )


def test_materialize_realized_outcomes_cli_writes_output(tmp_path: Path) -> None:
    chain_path, metadata_path = _write_strict_snapshot(
        tmp_path,
        snapshot_id="spy-20260613-185808",
        expiration="2026-06-15",
        quote_observed_at="2026-06-13T18:58:08Z",
        as_of="2026-06-13",
    )
    manifest_path = _write_manifest(
        tmp_path,
        [
            {
                "snapshot_id": "spy-20260613-185808",
                "ticker": "SPY",
                "as_of": "2026-06-13",
                "chain_path": str(chain_path),
                "metadata_path": str(metadata_path),
            }
        ],
    )
    realized_underlying_path = tmp_path / "realized_underlying.csv"
    output_path = tmp_path / "realized_outcomes.csv"
    write_realized_underlying_frame(
        pd.DataFrame([_realized_underlying_row(event_date="2026-06-15", observed_price=741.25)]),
        realized_underlying_path,
    )

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--realized-underlying",
            str(realized_underlying_path),
            "--output",
            str(output_path),
        ]
    )

    output = pd.read_csv(output_path)
    assert exit_code == 0
    assert output["expiration"].tolist() == ["2026-06-15"]
    assert output["realized_terminal_underlying_price"].tolist() == [741.25]


def test_materialize_realized_outcomes_from_manifest_excludes_future_expirations_as_of_2026_08_23(
    tmp_path: Path,
) -> None:
    chain_past, metadata_past = _write_strict_snapshot(
        tmp_path,
        snapshot_id="spy-20260613-185808",
        expiration="2026-06-15",
        quote_observed_at="2026-06-13T18:58:08Z",
        as_of="2026-06-13",
    )
    chain_future, metadata_future = _write_strict_snapshot(
        tmp_path,
        snapshot_id="spy-20260820-185808",
        expiration="2027-12-17",
        quote_observed_at="2026-08-20T18:58:08Z",
        as_of="2026-08-20",
    )
    manifest_path = _write_manifest(
        tmp_path,
        [
            {
                "snapshot_id": "spy-20260613-185808",
                "ticker": "SPY",
                "as_of": "2026-06-13",
                "chain_path": str(chain_past),
                "metadata_path": str(metadata_past),
            },
            {
                "snapshot_id": "spy-20260820-185808",
                "ticker": "SPY",
                "as_of": "2026-08-20",
                "chain_path": str(chain_future),
                "metadata_path": str(metadata_future),
            },
        ],
    )
    realized_underlying_path = tmp_path / "realized_underlying.csv"
    write_realized_underlying_frame(
        pd.DataFrame([_realized_underlying_row(event_date="2026-06-15", observed_price=741.25)]),
        realized_underlying_path,
    )

    artifacts = materialize_realized_outcomes_from_snapshot_manifest(
        manifest_path=manifest_path,
        realized_underlying_paths=[realized_underlying_path],
        realized_as_of="2026-08-23T12:00:00Z",
    )

    assert artifacts.required_observations["expiration"].tolist() == ["2026-06-15", "2027-12-17"]
    assert artifacts.eligible_required_observations["expiration"].tolist() == ["2026-06-15"]
    assert artifacts.future_required_observations["expiration"].tolist() == ["2027-12-17"]
    assert artifacts.outcomes["expiration"].dt.strftime("%Y-%m-%d").tolist() == ["2026-06-15"]
