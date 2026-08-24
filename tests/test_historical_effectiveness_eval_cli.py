from __future__ import annotations

from pathlib import Path

import pandas as pd

from options_edge_scanner.cli.historical_effectiveness_eval import main


def _write_trading_foundation_snapshot(
    root: Path,
    *,
    ticker: str = "SPY",
    snapshot_date: str = "2026-06-15",
    expiration_code: str = "260717",
) -> Path:
    snapshot_dir = root / ticker / "option_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{ticker}_options_snapshot_{snapshot_date}.csv"
    trade_timestamp = f"{snapshot_date}T19:55:00Z"
    pd.DataFrame(
        [
            {
                "option_symbol": f"{ticker}{expiration_code}C00595000",
                "implied_volatility": 0.16,
                "ask_price": 7.2,
                "bid_price": 6.8,
                "last_trade_time": trade_timestamp,
            },
            {
                "option_symbol": f"{ticker}{expiration_code}C00600000",
                "implied_volatility": 0.15,
                "ask_price": 5.7,
                "bid_price": 5.3,
                "last_trade_time": trade_timestamp,
            },
            {
                "option_symbol": f"{ticker}{expiration_code}C00605000",
                "implied_volatility": 0.14,
                "ask_price": 4.2,
                "bid_price": 3.8,
                "last_trade_time": trade_timestamp,
            },
            {
                "option_symbol": f"{ticker}{expiration_code}P00595000",
                "implied_volatility": 0.16,
                "ask_price": 1.7,
                "bid_price": 1.3,
                "last_trade_time": trade_timestamp,
            },
            {
                "option_symbol": f"{ticker}{expiration_code}P00600000",
                "implied_volatility": 0.17,
                "ask_price": 2.9,
                "bid_price": 2.5,
                "last_trade_time": trade_timestamp,
            },
            {
                "option_symbol": f"{ticker}{expiration_code}P00605000",
                "implied_volatility": 0.18,
                "ask_price": 4.2,
                "bid_price": 3.8,
                "last_trade_time": trade_timestamp,
            },
        ]
    ).to_csv(path, index=False)
    return path


def _write_trading_foundation_eod(
    root: Path,
    *,
    ticker: str = "SPY",
) -> Path:
    eod_dir = root / ticker / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    path = eod_dir / f"{ticker}_1D.csv"
    pd.DataFrame(
        [
            {
                "close": 600.0,
                "t": "2026-06-15T04:00:00Z",
                "symbol": ticker,
            },
            {
                "close": 610.0,
                "t": "2026-07-17T04:00:00Z",
                "symbol": ticker,
            },
        ]
    ).to_csv(path, index=False)
    return path


def test_historical_effectiveness_eval_cli_writes_end_to_end_artifacts(tmp_path: Path) -> None:
    historical_data_root = tmp_path / "historical_data"
    _write_trading_foundation_snapshot(historical_data_root)
    _write_trading_foundation_eod(historical_data_root)
    output_dir = tmp_path / "study"

    exit_code = main(
        [
            "--historical-data-root",
            str(historical_data_root),
            "--ticker",
            "SPY",
            "--snapshot-date",
            "2026-06-15",
            "--realized-as-of",
            "2026-08-23T12:00:00Z",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0

    summary = pd.read_csv(output_dir / "effectiveness_summary.csv")
    observations = pd.read_csv(output_dir / "effectiveness_observations.csv")
    report = (output_dir / "historical_effectiveness_report.md").read_text(encoding="utf-8")

    assert len(summary) == 1
    assert not observations.empty
    assert "mean_realized_pnl_executable" in summary.columns
    assert int(summary.loc[0, "evaluated_opportunity_count"]) == len(observations)
    assert "Historical Effectiveness Run" in report
    assert (output_dir / "calibration_summary.csv").exists()
    assert (output_dir / "effectiveness_metric_buckets.csv").exists()
    assert (output_dir / "effectiveness_execution_sensitivity.csv").exists()


def test_historical_effectiveness_eval_cli_preserves_exclusions_when_some_realized_dates_are_missing(
    tmp_path: Path,
) -> None:
    historical_data_root = tmp_path / "historical_data"
    _write_trading_foundation_snapshot(
        historical_data_root,
        snapshot_date="2026-06-15",
        expiration_code="260717",
    )
    _write_trading_foundation_snapshot(
        historical_data_root,
        snapshot_date="2026-06-16",
        expiration_code="260724",
    )
    eod_dir = historical_data_root / "SPY" / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"close": 600.0, "t": "2026-06-15T04:00:00Z", "symbol": "SPY"},
            {"close": 602.0, "t": "2026-06-16T04:00:00Z", "symbol": "SPY"},
            {"close": 610.0, "t": "2026-07-17T04:00:00Z", "symbol": "SPY"},
        ]
    ).to_csv(eod_dir / "SPY_1D.csv", index=False)
    output_dir = tmp_path / "study_partial"

    exit_code = main(
        [
            "--historical-data-root",
            str(historical_data_root),
            "--ticker",
            "SPY",
            "--snapshot-date",
            "2026-06-15",
            "--snapshot-date",
            "2026-06-16",
            "--realized-as-of",
            "2026-08-23T12:00:00Z",
            "--output-dir",
            str(output_dir),
        ]
    )

    summary = pd.read_csv(output_dir / "effectiveness_summary.csv")
    observations = pd.read_csv(output_dir / "effectiveness_observations.csv")
    exclusions = pd.read_csv(output_dir / "effectiveness_exclusions.csv")
    exclusion_summary = pd.read_csv(output_dir / "effectiveness_exclusion_summary.csv")
    coverage_audit = pd.read_csv(output_dir / "realized_outcome_coverage_audit.csv")
    report = (output_dir / "historical_effectiveness_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert int(summary.loc[0, "evaluated_opportunity_count"]) == len(observations)
    assert int(summary.loc[0, "excluded_opportunity_count"]) == len(exclusions)
    assert int(summary.loc[0, "excluded_missing_realized_underlying_count"]) == len(exclusions)
    assert summary.loc[0, "missing_realized_event_dates"] == "2026-07-24"
    assert set(exclusions["exclusion_reason"]) == {"missing_realized_underlying"}
    assert set(exclusions["required_event_date"]) == {"2026-07-24"}
    assert set(exclusion_summary["required_event_date"]) == {"2026-07-24"}
    assert set(coverage_audit["event_date"]) == {"2026-07-17", "2026-07-24"}
    assert coverage_audit.loc[
        coverage_audit["event_date"] == "2026-07-24",
        "status",
    ].iloc[0] == "missing"
    assert "2026-07-24" in report
