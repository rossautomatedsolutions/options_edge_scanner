from __future__ import annotations

from pathlib import Path

import pandas as pd

from options_edge_scanner.backtest.runner import BACKTEST_EXIT_FIXTURE_COLUMNS


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SIGNALS_PATH = FIXTURES_DIR / "sample_backtest_signals.csv"
TRADE_RESULTS_PATH = FIXTURES_DIR / "sample_backtest_trade_results.csv"
SUMMARY_PATH = FIXTURES_DIR / "sample_backtest_summary.csv"
EXIT_FIXTURES_PATH = FIXTURES_DIR / "sample_backtest_exit_fixtures.csv"


BACKTEST_SIGNAL_COLUMNS = [
    "signal_id",
    "as_of",
    "ticker",
    "expiration",
    "spread_type",
    "lower_strike",
    "upper_strike",
    "debit",
    "max_profit",
    "max_loss",
    "expected_value",
    "probability_of_profit",
]

BACKTEST_TRADE_RESULT_COLUMNS = [
    "signal_id",
    "ticker",
    "entry_date",
    "exit_date",
    "exit_reason",
    "fill_price_assumption",
    "realized_pnl",
    "max_profit",
    "max_loss",
    "outcome_label",
]

BACKTEST_SUMMARY_COLUMNS = [
    "run_id",
    "signal_count",
    "trade_count",
    "win_count",
    "loss_count",
    "total_expected_value",
    "total_realized_pnl",
    "notes",
]

def test_backtest_signal_fixture_has_required_columns() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    assert list(signals.columns) == BACKTEST_SIGNAL_COLUMNS
    assert pd.to_numeric(signals["expected_value"], errors="coerce").notna().all()
    assert pd.to_numeric(signals["probability_of_profit"], errors="coerce").notna().all()


def test_backtest_trade_result_fixture_references_signal_ids() -> None:
    signals = pd.read_csv(SIGNALS_PATH)
    trade_results = pd.read_csv(TRADE_RESULTS_PATH)

    assert list(trade_results.columns) == BACKTEST_TRADE_RESULT_COLUMNS
    assert set(trade_results["signal_id"]).issubset(set(signals["signal_id"]))
    assert pd.to_numeric(trade_results["realized_pnl"], errors="coerce").notna().all()


def test_backtest_summary_fixture_matches_fixture_counts() -> None:
    signals = pd.read_csv(SIGNALS_PATH)
    trade_results = pd.read_csv(TRADE_RESULTS_PATH)
    summary = pd.read_csv(SUMMARY_PATH)

    assert list(summary.columns) == BACKTEST_SUMMARY_COLUMNS
    assert len(summary) == 1
    assert int(summary.iloc[0]["signal_count"]) == len(signals)
    assert int(summary.iloc[0]["trade_count"]) == len(trade_results)
    assert pd.to_numeric(summary["total_expected_value"], errors="coerce").notna().all()
    assert pd.to_numeric(summary["total_realized_pnl"], errors="coerce").notna().all()


def test_backtest_exit_fixture_exists_and_has_required_columns() -> None:
    signals = pd.read_csv(SIGNALS_PATH)
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH)

    assert EXIT_FIXTURES_PATH.exists()
    assert list(exit_fixtures.columns) == BACKTEST_EXIT_FIXTURE_COLUMNS
    assert set(exit_fixtures["signal_id"]).issubset(set(signals["signal_id"]))


def test_backtest_exit_fixture_parses_dates_and_numeric_fields() -> None:
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH)

    assert pd.to_datetime(exit_fixtures["exit_date"], errors="coerce").notna().all()
    assert pd.to_numeric(exit_fixtures["exit_underlying_price"], errors="coerce").notna().all()
    assert pd.to_numeric(exit_fixtures["exit_spread_value"], errors="coerce").notna().all()


def test_backtest_exit_fixture_notes_are_clearly_local_offline_placeholders() -> None:
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH)
    notes = exit_fixtures["fixture_notes"].astype("string").str.lower()

    assert notes.str.contains("local").all()
    assert notes.str.contains("offline").all()
    assert notes.str.contains("placeholder").all()
