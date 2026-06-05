"""Minimal research-only backtest contract adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


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

BACKTEST_EXIT_FIXTURE_COLUMNS = [
    "signal_id",
    "exit_date",
    "exit_underlying_price",
    "exit_spread_value",
    "exit_reason",
    "fixture_notes",
]

_NUMERIC_SIGNAL_COLUMNS = (
    "lower_strike",
    "upper_strike",
    "debit",
    "max_profit",
    "max_loss",
    "expected_value",
    "probability_of_profit",
)

_NUMERIC_EXIT_FIXTURE_COLUMNS = (
    "exit_underlying_price",
    "exit_spread_value",
)

_PLACEHOLDER_EXIT_REASON = "expiration_placeholder"
_PLACEHOLDER_OUTCOME_LABEL = "placeholder_flat"
_PLACEHOLDER_NOTES = (
    "Contract adapter only. Placeholder outputs assume entry at debit, expiration-based exit, "
    "and realized_pnl=0.0. No historical fills, exits, or pricing are implemented."
)


def _empty_trade_results_frame() -> pd.DataFrame:
    """Return an empty trade-result frame with canonical columns."""
    return pd.DataFrame(columns=BACKTEST_TRADE_RESULT_COLUMNS)


def _empty_summary_frame() -> pd.DataFrame:
    """Return an empty summary frame with canonical columns."""
    return pd.DataFrame(columns=BACKTEST_SUMMARY_COLUMNS)


def calculate_placeholder_realized_pnl(row: pd.Series) -> float:
    """Return the deterministic placeholder realized PnL for a signal row."""
    _ = row
    return 0.0


def classify_placeholder_outcome(realized_pnl: float) -> str:
    """Return the deterministic placeholder outcome label for a realized PnL."""
    _ = realized_pnl
    return _PLACEHOLDER_OUTCOME_LABEL


def build_placeholder_exit_reason() -> str:
    """Return the deterministic placeholder exit-reason label."""
    return _PLACEHOLDER_EXIT_REASON


def validate_backtest_signal_frame(signals: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a dataframe against the BacktestSignalRow contract."""
    working = signals.copy()

    missing_columns = [column for column in BACKTEST_SIGNAL_COLUMNS if column not in working.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required BacktestSignalRow columns: {missing}")

    working["signal_id"] = working["signal_id"].astype("string")
    working["ticker"] = working["ticker"].astype("string").str.upper()
    working["spread_type"] = working["spread_type"].astype("string").str.strip().str.lower()
    working["as_of"] = pd.to_datetime(working["as_of"], errors="coerce")
    working["expiration"] = pd.to_datetime(working["expiration"], errors="coerce")

    for column in _NUMERIC_SIGNAL_COLUMNS:
        working[column] = pd.to_numeric(working[column], errors="coerce")

    return working.loc[:, BACKTEST_SIGNAL_COLUMNS].reset_index(drop=True)


def validate_backtest_exit_fixture_frame(exit_fixtures: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a dataframe against the BacktestExitFixtureRow contract."""
    working = exit_fixtures.copy()

    missing_columns = [column for column in BACKTEST_EXIT_FIXTURE_COLUMNS if column not in working.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required BacktestExitFixtureRow columns: {missing}")

    working["signal_id"] = working["signal_id"].astype("string")
    working["exit_reason"] = working["exit_reason"].astype("string").str.strip()
    working["fixture_notes"] = working["fixture_notes"].astype("string").str.strip()
    working["exit_date"] = pd.to_datetime(working["exit_date"], errors="coerce")

    for column in _NUMERIC_EXIT_FIXTURE_COLUMNS:
        working[column] = pd.to_numeric(working[column], errors="coerce")

    return working.loc[:, BACKTEST_EXIT_FIXTURE_COLUMNS].reset_index(drop=True)


def load_backtest_exit_fixtures(path: str | Path) -> pd.DataFrame:
    """Load contract-compliant backtest exit fixtures from a local CSV file."""
    file_path = Path(path)
    exit_fixtures = pd.read_csv(file_path)
    return validate_backtest_exit_fixture_frame(exit_fixtures)


def build_placeholder_trade_results(signals: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """Build deterministic placeholder BacktestTradeResultRow outputs from signals."""
    _ = run_id
    validated = validate_backtest_signal_frame(signals)
    if validated.empty:
        return _empty_trade_results_frame()

    realized_pnl = validated.apply(calculate_placeholder_realized_pnl, axis=1)
    outcome_label = realized_pnl.apply(classify_placeholder_outcome)
    exit_reason = build_placeholder_exit_reason()

    trade_results = pd.DataFrame(
        {
            "signal_id": validated["signal_id"],
            "ticker": validated["ticker"],
            "entry_date": validated["as_of"],
            "exit_date": validated["expiration"],
            "exit_reason": exit_reason,
            "fill_price_assumption": validated["debit"],
            "realized_pnl": realized_pnl,
            "max_profit": validated["max_profit"],
            "max_loss": validated["max_loss"],
            "outcome_label": outcome_label,
        }
    )
    return trade_results.loc[:, BACKTEST_TRADE_RESULT_COLUMNS].reset_index(drop=True)


def summarize_placeholder_backtest(
    trade_results: pd.DataFrame,
    signals: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    """Build a one-row BacktestSummaryRow placeholder summary."""
    validated_signals = validate_backtest_signal_frame(signals)
    working_results = trade_results.copy()
    if working_results.empty:
        working_results = _empty_trade_results_frame()

    missing_columns = [column for column in BACKTEST_TRADE_RESULT_COLUMNS if column not in working_results.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required BacktestTradeResultRow columns: {missing}")

    working_results["realized_pnl"] = pd.to_numeric(working_results["realized_pnl"], errors="coerce")
    working_results["outcome_label"] = working_results["outcome_label"].astype("string")

    summary = pd.DataFrame(
        [
            {
                "run_id": str(run_id),
                "signal_count": int(len(validated_signals)),
                "trade_count": int(len(working_results)),
                "win_count": int((working_results["outcome_label"] == "win").sum()),
                "loss_count": int((working_results["outcome_label"] == "loss").sum()),
                "total_expected_value": float(validated_signals["expected_value"].fillna(0.0).sum()),
                "total_realized_pnl": float(working_results["realized_pnl"].fillna(0.0).sum()),
                "notes": _PLACEHOLDER_NOTES,
            }
        ]
    )
    return summary.loc[:, BACKTEST_SUMMARY_COLUMNS].reset_index(drop=True)


def run_contract_backtest(
    signals: pd.DataFrame,
    run_id: str = "contract_backtest",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the minimal contract-only research backtest adapter."""
    validated = validate_backtest_signal_frame(signals)
    trade_results = build_placeholder_trade_results(validated, run_id=run_id)
    summary = summarize_placeholder_backtest(trade_results, validated, run_id=run_id)
    return trade_results, summary


def run_backtest(signals_frame: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper returning placeholder trade-result rows only."""
    trade_results, _summary = run_contract_backtest(signals_frame)
    return trade_results
