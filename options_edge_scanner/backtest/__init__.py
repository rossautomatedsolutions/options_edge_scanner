"""Backtesting package for evaluating scanner signals."""

from .runner import (
    BACKTEST_EXIT_FIXTURE_COLUMNS,
    BACKTEST_SIGNAL_COLUMNS,
    BACKTEST_SUMMARY_COLUMNS,
    BACKTEST_TRADE_RESULT_COLUMNS,
    build_placeholder_trade_results,
    build_placeholder_exit_reason,
    calculate_placeholder_realized_pnl,
    classify_placeholder_outcome,
    load_backtest_exit_fixtures,
    run_backtest,
    run_contract_backtest,
    summarize_placeholder_backtest,
    validate_backtest_exit_fixture_frame,
    validate_backtest_signal_frame,
)

__all__ = [
    "BACKTEST_EXIT_FIXTURE_COLUMNS",
    "BACKTEST_SIGNAL_COLUMNS",
    "BACKTEST_SUMMARY_COLUMNS",
    "BACKTEST_TRADE_RESULT_COLUMNS",
    "build_placeholder_trade_results",
    "build_placeholder_exit_reason",
    "calculate_placeholder_realized_pnl",
    "classify_placeholder_outcome",
    "load_backtest_exit_fixtures",
    "run_backtest",
    "run_contract_backtest",
    "summarize_placeholder_backtest",
    "validate_backtest_exit_fixture_frame",
    "validate_backtest_signal_frame",
]
