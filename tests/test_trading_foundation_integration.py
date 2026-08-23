from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from options_edge_scanner.calibration.materialization import (
    materialize_realized_outcomes_from_snapshot_manifest,
)
from options_edge_scanner.cli.historical_snapshot_scan import run_historical_snapshot_scan
from options_edge_scanner.data.historical_snapshot_loader import load_historical_snapshots
from options_edge_scanner.data.loader import validate_option_quote_frame
from options_edge_scanner.data.trading_foundation import (
    TRADING_FOUNDATION_DAY_PRECISION_POLICY,
    build_trading_foundation_snapshot_id,
    write_trading_foundation_realized_underlying,
    write_trading_foundation_snapshot_manifest,
)


def _write_trading_foundation_snapshot(
    root: Path,
    *,
    ticker: str = "SPY",
    snapshot_date: str = "2026-06-15",
    frame_mutator=None,
) -> Path:
    snapshot_dir = root / ticker / "option_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{ticker}_options_snapshot_{snapshot_date}.csv"
    frame = pd.DataFrame(
        [
            {
                "option_symbol": "SPY260717C00595000",
                "delta": 0.42,
                "gamma": 0.02,
                "theta": -0.05,
                "vega": 0.10,
                "implied_volatility": 0.16,
                "ask_price": 7.2,
                "ask_size": 10,
                "bid_price": 6.8,
                "bid_size": 10,
                "last_trade_price": 7.0,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717C00600000",
                "delta": 0.30,
                "gamma": 0.01,
                "theta": -0.04,
                "vega": 0.08,
                "implied_volatility": 0.15,
                "ask_price": 5.7,
                "ask_size": 10,
                "bid_price": 5.3,
                "bid_size": 10,
                "last_trade_price": 5.5,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717C00605000",
                "delta": 0.18,
                "gamma": 0.02,
                "theta": -0.03,
                "vega": 0.07,
                "implied_volatility": 0.14,
                "ask_price": 4.2,
                "ask_size": 10,
                "bid_price": 3.8,
                "bid_size": 10,
                "last_trade_price": 4.0,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717C00610000",
                "delta": 0.12,
                "gamma": 0.01,
                "theta": -0.02,
                "vega": 0.06,
                "implied_volatility": 0.13,
                "ask_price": 3.7,
                "ask_size": 10,
                "bid_price": 3.3,
                "bid_size": 10,
                "last_trade_price": 3.5,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717P00595000",
                "delta": -0.12,
                "gamma": 0.01,
                "theta": -0.04,
                "vega": 0.10,
                "implied_volatility": 0.16,
                "ask_price": 1.7,
                "ask_size": 10,
                "bid_price": 1.3,
                "bid_size": 10,
                "last_trade_price": 1.5,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717P00600000",
                "delta": -0.22,
                "gamma": 0.02,
                "theta": -0.05,
                "vega": 0.09,
                "implied_volatility": 0.17,
                "ask_price": 2.9,
                "ask_size": 10,
                "bid_price": 2.5,
                "bid_size": 10,
                "last_trade_price": 2.7,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717P00605000",
                "delta": -0.31,
                "gamma": 0.02,
                "theta": -0.06,
                "vega": 0.11,
                "implied_volatility": 0.18,
                "ask_price": 4.2,
                "ask_size": 10,
                "bid_price": 3.8,
                "bid_size": 10,
                "last_trade_price": 4.0,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
            {
                "option_symbol": "SPY260717P00610000",
                "delta": -0.36,
                "gamma": 0.02,
                "theta": -0.07,
                "vega": 0.12,
                "implied_volatility": 0.19,
                "ask_price": 4.9,
                "ask_size": 10,
                "bid_price": 4.5,
                "bid_size": 10,
                "last_trade_price": 4.7,
                "last_trade_size": 1,
                "last_trade_time": "2026-06-15T19:55:00Z",
            },
        ]
    )
    if frame_mutator is not None:
        frame = frame_mutator(frame.copy())
    frame.to_csv(path, index=False)
    return path


def _write_trading_foundation_eod(
    root: Path,
    *,
    ticker: str = "SPY",
    rows: list[dict[str, object]] | None = None,
) -> Path:
    eod_dir = root / ticker / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    path = eod_dir / f"{ticker}_1D.csv"
    if rows is None:
        rows = [
            {
                "close": 600.0,
                "high": 602.0,
                "low": 598.0,
                "n": 1,
                "open": 599.0,
                "t": "2026-06-15T04:00:00Z",
                "volume": 100,
                "vw": 600.0,
                "symbol": ticker,
            },
            {
                "close": 610.0,
                "high": 612.0,
                "low": 608.0,
                "n": 1,
                "open": 609.0,
                "t": "2026-07-17T04:00:00Z",
                "volume": 100,
                "vw": 610.0,
                "symbol": ticker,
            },
        ]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_validate_option_quote_frame_parses_occ_option_symbol_and_trading_foundation_price_aliases() -> None:
    frame = pd.DataFrame(
        [
            {
                "option_symbol": "SPY260717C00600000",
                "bid_price": 6.0,
                "ask_price": 6.4,
                "implied_volatility": 0.22,
            }
        ]
    )

    validated = validate_option_quote_frame(
        frame,
        require_underlying_price=False,
        default_ticker="SPY",
    )

    assert validated["ticker"].tolist() == ["SPY"]
    assert validated["expiration"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-17"]
    assert validated["strike"].tolist() == [600.0]
    assert validated["type"].tolist() == ["call"]
    assert validated["bid"].tolist() == [6.0]
    assert validated["ask"].tolist() == [6.4]
    assert validated["mid"].tolist() == [6.2]


def test_trading_foundation_manifest_builder_supports_strict_snapshot_loading(tmp_path: Path) -> None:
    historical_data_root = tmp_path / "historical_data"
    _write_trading_foundation_snapshot(historical_data_root)
    _write_trading_foundation_eod(historical_data_root)
    manifest_path = tmp_path / "tf_manifest.csv"

    artifacts = write_trading_foundation_snapshot_manifest(
        historical_data_root,
        ticker="SPY",
        snapshot_dates=["2026-06-15"],
        manifest_output_path=manifest_path,
    )

    manifest = pd.read_csv(artifacts.manifest_path)
    metadata = json.loads(artifacts.metadata_paths[0].read_text(encoding="utf-8"))
    snapshots = load_historical_snapshots(artifacts.manifest_path)

    assert manifest["snapshot_id"].tolist() == [build_trading_foundation_snapshot_id(ticker="SPY", snapshot_date="2026-06-15")]
    assert metadata["quote_observed_at_policy"] == TRADING_FOUNDATION_DAY_PRECISION_POLICY
    assert metadata["underlying_price"] == 600.0
    assert metadata["underlying_price_raw_timestamp"] == "2026-06-15T04:00:00Z"
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.option_quotes["ticker"].unique().tolist() == ["SPY"]
    assert snapshot.option_quotes["expiration"].dt.strftime("%Y-%m-%d").unique().tolist() == ["2026-07-17"]
    assert snapshot.option_quotes["underlying_price"].unique().tolist() == [600.0]


def test_trading_foundation_snapshot_manifest_and_eod_export_support_scan_and_outcomes(
    tmp_path: Path,
) -> None:
    historical_data_root = tmp_path / "historical_data"
    _write_trading_foundation_snapshot(historical_data_root)
    _write_trading_foundation_eod(historical_data_root)

    manifest_path = tmp_path / "tf_manifest.csv"
    manifest_artifacts = write_trading_foundation_snapshot_manifest(
        historical_data_root,
        ticker="SPY",
        snapshot_dates=["2026-06-15"],
        manifest_output_path=manifest_path,
    )
    realized_underlying_path = tmp_path / "tf_realized_underlying.csv"
    observations = write_trading_foundation_realized_underlying(
        historical_data_root,
        ticker="SPY",
        start_date="2026-07-17",
        end_date="2026-07-17",
        output_path=realized_underlying_path,
        acquired_at="2026-08-23T12:00:00Z",
    )
    candidates_path = tmp_path / "tf_candidates.csv"
    summary_path = tmp_path / "tf_summary.csv"
    candidates, summary = run_historical_snapshot_scan(
        manifest_artifacts.manifest_path,
        output_path=candidates_path,
        summary_output_path=summary_path,
    )
    outcome_artifacts = materialize_realized_outcomes_from_snapshot_manifest(
        manifest_path=manifest_artifacts.manifest_path,
        realized_underlying_paths=[realized_underlying_path],
    )

    assert len(observations) == 1
    assert observations["observed_price"].tolist() == [610.0]
    assert summary["status"].tolist() == ["success"]
    assert not candidates.empty
    assert outcome_artifacts.required_observations["expiration"].tolist() == ["2026-07-17"]
    assert outcome_artifacts.outcomes["realized_terminal_underlying_price"].tolist() == [610.0]


def test_trading_foundation_snapshot_scan_skips_nonfinite_iv_contracts_without_failing_snapshot(
    tmp_path: Path,
) -> None:
    historical_data_root = tmp_path / "historical_data"
    _write_trading_foundation_snapshot(
        historical_data_root,
        frame_mutator=lambda frame: frame.assign(
            implied_volatility=frame["implied_volatility"].where(frame["option_symbol"] != "SPY260717C00600000", float("nan"))
        ),
    )
    _write_trading_foundation_eod(historical_data_root)

    manifest_artifacts = write_trading_foundation_snapshot_manifest(
        historical_data_root,
        ticker="SPY",
        snapshot_dates=["2026-06-15"],
        manifest_output_path=tmp_path / "tf_manifest.csv",
    )
    candidates, summary = run_historical_snapshot_scan(
        manifest_artifacts.manifest_path,
        output_path=tmp_path / "tf_candidates.csv",
        summary_output_path=tmp_path / "tf_summary.csv",
    )

    assert summary["status"].tolist() == ["success"]
    assert not candidates.empty
    assert candidates["implied_volatility"].notna().all()
    assert candidates["probability_of_profit"].map(
        lambda value: pd.notna(value) and math.isfinite(float(value))
    ).all()


def test_trading_foundation_realized_underlying_manifest_export_excludes_future_expirations_as_of_2026_08_23(
    tmp_path: Path,
) -> None:
    historical_data_root = tmp_path / "historical_data"
    _write_trading_foundation_snapshot(
        historical_data_root,
        snapshot_date="2026-06-15",
    )
    _write_trading_foundation_snapshot(
        historical_data_root,
        snapshot_date="2026-08-20",
        frame_mutator=lambda frame: frame.assign(
            option_symbol=frame["option_symbol"].str.replace("260717", "271217", regex=False)
        ),
    )
    _write_trading_foundation_eod(
        historical_data_root,
        rows=[
            {
                "close": 600.0,
                "high": 602.0,
                "low": 598.0,
                "n": 1,
                "open": 599.0,
                "t": "2026-06-15T04:00:00Z",
                "volume": 100,
                "vw": 600.0,
                "symbol": "SPY",
            },
            {
                "close": 605.0,
                "high": 607.0,
                "low": 603.0,
                "n": 1,
                "open": 604.0,
                "t": "2026-08-20T04:00:00Z",
                "volume": 100,
                "vw": 605.0,
                "symbol": "SPY",
            },
            {
                "close": 610.0,
                "high": 612.0,
                "low": 608.0,
                "n": 1,
                "open": 609.0,
                "t": "2026-07-17T04:00:00Z",
                "volume": 100,
                "vw": 610.0,
                "symbol": "SPY",
            },
        ],
    )

    manifest_artifacts = write_trading_foundation_snapshot_manifest(
        historical_data_root,
        ticker="SPY",
        snapshot_dates=["2026-06-15", "2026-08-20"],
        manifest_output_path=tmp_path / "tf_manifest.csv",
    )
    output_path = tmp_path / "tf_realized_underlying.csv"
    observations = write_trading_foundation_realized_underlying(
        historical_data_root,
        ticker="SPY",
        manifest_path=manifest_artifacts.manifest_path,
        realized_as_of="2026-08-23T12:00:00Z",
        output_path=output_path,
        acquired_at="2026-08-23T12:00:00Z",
    )

    written = pd.read_csv(output_path)
    assert observations["event_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-17"]
    assert written["event_date"].tolist() == ["2026-07-17"]
