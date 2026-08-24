# Historical Effectiveness Contracts

This repo now includes a research-only historical effectiveness framework for the maintained Options Edge Scanner baseline.
It is deliberately narrower than a full backtester:

- it evaluates the existing ranked scanner output honestly instead of replacing the ranking
- it preserves strict point-in-time snapshot loading and separate realized-outcome materialization
- it measures hold-to-expiration economics only
- it does not infer intraday fills, exits, or option lifecycle marks

## Purpose

The effectiveness workflow is meant to answer questions such as:

- does `ranking_score` discriminate better versus worse subsequent outcomes?
- does `expected_value` line up with realized expiration-held economic value?
- do higher score or EV buckets outperform lower ones?
- do results survive conservative executable entry assumptions?
- are results concentrated in a few tail observations?

## Inputs

The maintained effectiveness path reuses existing repo contracts rather than creating a new scanner surface.

Primary inputs:

- strict historical snapshot manifest consumed by `options_edge_scanner.cli.historical_snapshot_scan`
- canonical Trading Foundation `historical_data/<TICKER>/option_snapshot/*.csv` files for opportunity reconstruction
- canonical Trading Foundation `historical_data/<TICKER>/eod/<TICKER>_1D.csv` for realized expiration-close outcomes
- `ScannerOpportunityRow` output from the maintained historical scanner
- separate `RealizedOutcomeRow` artifacts from `materialize_realized_outcomes(...)`

## Realized Economic Labeling

The effectiveness evaluator labels each scanner opportunity against the realized terminal underlying price already materialized in a separate outcome artifact.

Current payoff convention:

- `bull_call_debit`: realized expiration spread value is `max(S_T - lower, 0) - max(S_T - upper, 0)`
- `bear_put_debit`: realized expiration spread value is `max(upper - S_T, 0) - max(lower - S_T, 0)`
- spread value is clipped to `[0, width]`

Current realized PnL surfaces:

- `realized_pnl_quoted`: expiration spread value minus `quoted_debit`, then minus the repo-wide `TRANSACTION_COST`
- `realized_pnl_executable`: expiration spread value minus execution-adjusted `debit`, then minus `TRANSACTION_COST`
- `realized_pnl_ask`: expiration spread value minus `spread_ask`, then minus `TRANSACTION_COST` when a displayed ask exists

This means effectiveness is measured against the repo's existing executable-entry assumptions, not a new execution model.

## EffectivenessObservationRow

The row-level output combines scanner opportunity fields, prediction timing fields, realized outcome fields, and derived effectiveness labels.

Important columns include:

- identity and timing: `prediction_id`, `snapshot_id`, `prediction_timestamp`, `quote_observed_at`, `as_of`, `expiration`
- structure: `spread_type`, `lower_strike`, `upper_strike`, `long_strike`, `short_strike`, `width`
- baseline economics: `debit`, `quoted_debit`, `expected_value`, `ranking_score`, `probability_of_profit`
- execution diagnostics: `spread_bid`, `spread_ask`, `spread_market_width`, `entry_slippage`, `liquidity_score`
- realized outcomes: `realized_terminal_underlying_price`, `realized_outcome_observed_at`, `realized_event`
- realized economics: `spread_expiration_value`, `realized_pnl_quoted`, `realized_pnl_executable`, `realized_pnl_ask`
- derived research buckets: `dte_bucket`, `breakeven_moneyness_bucket`, `liquidity_bucket`, `spread_width_bucket`, `volatility_regime_bucket`, `prediction_quarter`

## Summary Artifacts

The evaluator writes machine-readable artifacts for both calibration and effectiveness.

Calibration artifacts:

- `probability_predictions.csv`
- `calibration_summary.csv`
- `calibration_bins.csv`
- `calibration_observations.csv`

Effectiveness artifacts:

- `effectiveness_summary.csv`
- `effectiveness_observations.csv`
- `effectiveness_metric_buckets.csv`
- `effectiveness_segment_summary.csv`
- `effectiveness_execution_sensitivity.csv`
- `effectiveness_tail_concentration.csv`
- `historical_effectiveness_report.md`

## Bucket And Segment Surfaces

Default ordered metric buckets:

- `ranking_score`
- `expected_value`
- `probability_of_profit`

Default segment cuts:

- `days_to_expiration`
- `spread_type`
- breakeven moneyness versus underlying
- liquidity score
- spread width relative to quoted debit
- implied volatility regime
- calendar quarter of prediction timestamp

The CLI can also evaluate additional future columns incrementally, such as:

- `relative_value_score`
- `greek_surface_anomaly_score`

Those are optional future metrics only. They are not required for the baseline framework.

## Current Boundary

What this framework does:

- evaluates the maintained baseline scanner honestly
- preserves strict historical snapshot and outcome separation
- produces calibration, discrimination, bucket, sensitivity, and tail-concentration artifacts
- supports one command that builds a manifest from canonical Trading Foundation files when needed and writes a full reviewable study package

What it does not do:

- replace ranking weights
- optimize ranking weights
- reconstruct historical opportunities from current chains
- simulate intraday entries or exits
- mark options through time between entry and expiration
- act as a portfolio backtester

## Main CLI

The end-to-end research entrypoint is:

```powershell
python -m options_edge_scanner.cli.historical_effectiveness_eval `
  --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data `
  --ticker SPY `
  --start-date 2025-05-27 `
  --end-date 2025-05-30 `
  --realized-as-of 2026-08-24T12:00:00Z `
  --output-dir outputs\historical_effectiveness\spy_20250527_20250530
```

That one command:

- builds a strict manifest when one is not supplied
- runs the maintained historical scanner
- normalizes realized underlying observations from canonical Trading Foundation EOD data
- materializes realized outcomes as of the explicit cutoff
- exports calibration artifacts
- evaluates realized expiration-held effectiveness for the baseline scanner
- writes a reviewable markdown report plus machine-readable CSV artifacts
