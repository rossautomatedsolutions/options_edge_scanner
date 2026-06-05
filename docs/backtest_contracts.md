# Backtest Contracts

This document defines the first minimal research-only backtest dataframe contracts for future offline historical analysis. These contracts are designed to line up with `ScannerOpportunityRow` output while avoiding any implication of live trading, brokerage routing, or execution promises.

Current implementation status:

- `options_edge_scanner/backtest/runner.py` is a contract adapter only
- it emits placeholder-shaped `BacktestTradeResultRow` and `BacktestSummaryRow` dataframes for downstream development
- it now isolates placeholder accounting hooks for realized PnL, outcome classification, and exit labeling
- exit fixtures can now be loaded and validated through opt-in helper functions
- it does not implement real historical fills
- it does not implement real exit rules
- it does not implement historical option pricing or lifecycle modeling

## Scope And Boundary

- offline historical and research use only
- no trade recommendation language
- no broker integration
- no order placement
- no alerting or autonomous execution
- no intraday execution modeling yet
- fill price is a placeholder assumption only
- expiration and exit handling are placeholders only
- max profit and max loss accounting are placeholders until the backtest runner is implemented

## BacktestSignalRow

Minimal candidate row passed from research scanner output into a future backtest workflow.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `signal_id` | string | Stable identifier for linking signals to trade results. |
| `as_of` | date-like | Research observation date used to generate the signal. |
| `ticker` | string | Underlying symbol. |
| `expiration` | date-like | Option expiration date from `ScannerOpportunityRow`. |
| `spread_type` | string | Canonical vertical spread type. |
| `lower_strike` | float | Lower strike from scanner output. |
| `upper_strike` | float | Upper strike from scanner output. |
| `debit` | float | Debit placeholder for research accounting. |
| `max_profit` | float | Scanner-derived max profit placeholder. |
| `max_loss` | float | Scanner-derived max loss placeholder. |
| `expected_value` | float | Scanner-derived expected value. |
| `probability_of_profit` | float | Scanner-derived probability of profit. |

Compatibility notes:

- This contract is intended to be a thin projection of `ScannerOpportunityRow`.
- It does not imply that a signal should be traded.
- It is only a research artifact describing a historical candidate.

## BacktestTradeResultRow

Minimal row describing a hypothetical backtest outcome linked to a prior signal.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `signal_id` | string | Must reference a `BacktestSignalRow.signal_id`. |
| `ticker` | string | Underlying symbol. |
| `entry_date` | date-like | Placeholder historical entry date. |
| `exit_date` | date-like | Placeholder historical exit or expiration date. |
| `exit_reason` | string | Placeholder such as `expiration`, `time_stop`, or `research_exit`. |
| `fill_price_assumption` | float | Placeholder assumed net entry price. |
| `realized_pnl` | float | Placeholder realized PnL under the chosen research rule. |
| `max_profit` | float | Research max profit reference carried from the signal. |
| `max_loss` | float | Research max loss reference carried from the signal. |
| `outcome_label` | string | Placeholder outcome such as `win`, `loss`, or `partial`. |

Assumptions:

- Fill price is not a true execution model.
- Exit handling is not yet a true lifecycle model.
- Realized PnL is a placeholder research field until explicit backtest rules are implemented.
- The current contract adapter uses deterministic placeholder values and does not infer real trade outcomes.
- The current accounting hooks are intentionally non-economic and exist only to isolate where future offline fixture-based exit and accounting rules will plug in.

## BacktestExitFixtureRow

Deterministic local-only fixture row describing a hypothetical exit state that future offline backtest tests may consume.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `signal_id` | string | Must reference a `BacktestSignalRow.signal_id`. |
| `exit_date` | date-like | Fixture-supplied offline exit date for deterministic tests. |
| `exit_underlying_price` | float | Fixture-only placeholder underlying price at exit. |
| `exit_spread_value` | float | Fixture-only placeholder spread value at exit. |
| `exit_reason` | string | Offline fixture label such as `fixture_expiration` or `fixture_time_stop`. |
| `fixture_notes` | string | Must clearly describe offline/local/placeholder fixture provenance. |

Assumptions:

- This row is a local fixture input only and is not a market-data integration point.
- The numeric values do not imply real historical prices, fills, or executable quotes.
- The current runner does not consume this fixture yet.
- The opt-in helper path only loads and validates fixture rows; it does not calculate PnL or execution outcomes.
- Future work may use this contract to plug deterministic offline exit and accounting rules into the research-only runner.

## BacktestSummaryRow

Aggregate row summarizing one research backtest run.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `run_id` | string | Stable identifier for the research run. |
| `signal_count` | integer | Count of input signal rows. |
| `trade_count` | integer | Count of output trade-result rows. |
| `win_count` | integer | Placeholder count of winning rows. |
| `loss_count` | integer | Placeholder count of losing rows. |
| `total_expected_value` | float | Sum of signal-level expected values. |
| `total_realized_pnl` | float | Sum of result-level placeholder realized PnL. |
| `notes` | string | Short research note about assumptions or fixture provenance. |

Assumptions:

- This summary is for offline research bookkeeping only.
- It is not a performance report suitable for execution decisions.
- Metrics remain placeholders until the runner defines explicit fill, exit, and accounting rules.
- Current summary output is shaped for downstream development and fixture-driven integration, not historical performance analysis.
