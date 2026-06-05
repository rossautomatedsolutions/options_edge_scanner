from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.backtest.runner import (
    BACKTEST_EXIT_FIXTURE_COLUMNS,
    BACKTEST_SUMMARY_COLUMNS,
    BACKTEST_TRADE_RESULT_COLUMNS,
    build_placeholder_exit_reason,
    build_placeholder_trade_results,
    calculate_placeholder_realized_pnl,
    classify_placeholder_outcome,
    load_backtest_exit_fixtures,
    run_contract_backtest,
    validate_backtest_exit_fixture_frame,
    validate_backtest_signal_frame,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SIGNALS_PATH = FIXTURES_DIR / "sample_backtest_signals.csv"
EXIT_FIXTURES_PATH = FIXTURES_DIR / "sample_backtest_exit_fixtures.csv"


def test_run_contract_backtest_accepts_valid_signal_fixture() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    trade_results, summary = run_contract_backtest(signals, run_id="fixture_contract_run")

    assert len(trade_results) == len(signals)
    assert len(summary) == 1
    assert summary.iloc[0]["run_id"] == "fixture_contract_run"


def test_calculate_placeholder_realized_pnl_returns_deterministic_zero() -> None:
    signals = validate_backtest_signal_frame(pd.read_csv(SIGNALS_PATH))

    realized_pnl = calculate_placeholder_realized_pnl(signals.iloc[0])

    assert realized_pnl == 0.0


def test_classify_placeholder_outcome_returns_flat_placeholder_for_zero() -> None:
    assert classify_placeholder_outcome(0.0) == "placeholder_flat"


def test_validate_backtest_exit_fixture_frame_accepts_valid_fixture() -> None:
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH)

    validated = validate_backtest_exit_fixture_frame(exit_fixtures)

    assert list(validated.columns) == BACKTEST_EXIT_FIXTURE_COLUMNS
    assert len(validated) == len(exit_fixtures)


def test_load_backtest_exit_fixtures_loads_and_validates_fixture() -> None:
    loaded = load_backtest_exit_fixtures(EXIT_FIXTURES_PATH)

    assert list(loaded.columns) == BACKTEST_EXIT_FIXTURE_COLUMNS
    assert loaded["signal_id"].tolist() == ["sig_001", "sig_002"]


def test_validate_backtest_exit_fixture_frame_raises_on_missing_required_columns() -> None:
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH).drop(columns=["fixture_notes", "exit_reason"])

    with pytest.raises(
        ValueError,
        match="Missing required BacktestExitFixtureRow columns: exit_reason, fixture_notes",
    ):
        validate_backtest_exit_fixture_frame(exit_fixtures)


def test_validate_backtest_exit_fixture_frame_normalizes_exit_date_deterministically() -> None:
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH)

    validated = validate_backtest_exit_fixture_frame(exit_fixtures)

    assert str(validated.loc[0, "exit_date"].date()) == "2026-02-13"
    assert str(validated.loc[1, "exit_date"].date()) == "2026-02-13"


def test_validate_backtest_exit_fixture_frame_normalizes_numeric_fields_deterministically() -> None:
    exit_fixtures = pd.read_csv(EXIT_FIXTURES_PATH)

    validated = validate_backtest_exit_fixture_frame(exit_fixtures)

    assert validated["exit_underlying_price"].tolist() == [101.5, 99.0]
    assert validated["exit_spread_value"].tolist() == [4.0, 1.5]


def test_validate_backtest_signal_frame_raises_on_missing_required_columns() -> None:
    signals = pd.read_csv(SIGNALS_PATH).drop(columns=["expected_value", "ticker"])

    with pytest.raises(
        ValueError,
        match="Missing required BacktestSignalRow columns: ticker, expected_value",
    ):
        validate_backtest_signal_frame(signals)


def test_run_contract_backtest_trade_results_match_contract_columns() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    trade_results, _summary = run_contract_backtest(signals)

    assert list(trade_results.columns) == BACKTEST_TRADE_RESULT_COLUMNS


def test_build_placeholder_trade_results_uses_helper_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    signals = pd.read_csv(SIGNALS_PATH)
    helper_calls: list[tuple[str, object]] = []

    def fake_realized_pnl(row: pd.Series) -> float:
        helper_calls.append(("pnl", row["signal_id"]))
        return 0.0

    def fake_outcome(realized_pnl: float) -> str:
        helper_calls.append(("outcome", realized_pnl))
        return "placeholder_flat"

    def fake_exit_reason() -> str:
        helper_calls.append(("exit_reason", None))
        return "expiration_placeholder"

    monkeypatch.setattr(
        "options_edge_scanner.backtest.runner.calculate_placeholder_realized_pnl",
        fake_realized_pnl,
    )
    monkeypatch.setattr(
        "options_edge_scanner.backtest.runner.classify_placeholder_outcome",
        fake_outcome,
    )
    monkeypatch.setattr(
        "options_edge_scanner.backtest.runner.build_placeholder_exit_reason",
        fake_exit_reason,
    )

    trade_results = build_placeholder_trade_results(signals, run_id="helper_contract_run")

    assert len([call for call in helper_calls if call[0] == "pnl"]) == len(signals)
    assert len([call for call in helper_calls if call[0] == "outcome"]) == len(signals)
    assert len([call for call in helper_calls if call[0] == "exit_reason"]) == 1
    assert set(trade_results["realized_pnl"]) == {0.0}
    assert set(trade_results["outcome_label"]) == {"placeholder_flat"}
    assert set(trade_results["exit_reason"]) == {"expiration_placeholder"}


def test_run_contract_backtest_summary_matches_contract_columns() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    _trade_results, summary = run_contract_backtest(signals)

    assert list(summary.columns) == BACKTEST_SUMMARY_COLUMNS


def test_run_contract_backtest_summary_counts_match_signal_and_result_rows() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    trade_results, summary = run_contract_backtest(signals)
    summary_row = summary.iloc[0]

    assert int(summary_row["signal_count"]) == len(signals)
    assert int(summary_row["trade_count"]) == len(trade_results)
    assert int(summary_row["win_count"]) == 0
    assert int(summary_row["loss_count"]) == 0


def test_run_contract_backtest_uses_explicit_deterministic_realized_pnl_placeholder() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    trade_results, summary = run_contract_backtest(signals)

    assert trade_results["realized_pnl"].tolist() == [0.0] * len(trade_results)
    assert float(summary.iloc[0]["total_realized_pnl"]) == 0.0
    assert "realized_pnl=0.0" in str(summary.iloc[0]["notes"])
    assert set(trade_results["exit_reason"]) == {"expiration_placeholder"}
    assert set(trade_results["outcome_label"]) == {"placeholder_flat"}


def test_summary_total_expected_value_still_sums_from_signals() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    _trade_results, summary = run_contract_backtest(signals)

    assert float(summary.iloc[0]["total_expected_value"]) == pytest.approx(signals["expected_value"].sum())


def test_build_placeholder_exit_reason_returns_placeholder_label() -> None:
    assert build_placeholder_exit_reason() == "expiration_placeholder"


def test_run_contract_backtest_behavior_remains_unchanged_with_exit_fixture_helpers_present() -> None:
    signals = pd.read_csv(SIGNALS_PATH)

    trade_results, summary = run_contract_backtest(signals, run_id="unchanged_contract_run")

    assert trade_results["realized_pnl"].tolist() == [0.0, 0.0]
    assert set(trade_results["exit_reason"]) == {"expiration_placeholder"}
    assert set(trade_results["outcome_label"]) == {"placeholder_flat"}
    assert float(summary.iloc[0]["total_realized_pnl"]) == 0.0
