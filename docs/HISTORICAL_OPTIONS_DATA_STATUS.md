# Historical Options Data Status

Date: Sunday, August 23, 2026
Repository: `C:\GitHub\options_edge_scanner`
Canonical upstream root for main-machine validation: `C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data`

## Repository Purpose

`options_edge_scanner` is a research-only offline scanner for deterministic debit vertical spread screening from point-in-time option opportunity sets, plus a narrow SPY expiration-close calibration workflow.

The maintained repo path does **not** currently do:

- full option lifecycle replay
- intraday execution simulation
- option OHLC-based exit modeling
- multi-symbol realized-outcome policy support
- portfolio backtesting

## Actual Historical-Data Requirement

The repo's maintained historical path needs:

- once-per-day historical option opportunity-set snapshots so it can reconstruct what contracts and quotes were available at the research date
- one aligned underlying spot value for each snapshot so moneyness, spread breakevens, and EV can be computed
- expiration-date daily underlying closes so SPY expiration outcomes can be materialized for calibration

The repo does **not** currently require:

- intraday option OHLC for exits
- multiple intraday chain snapshots
- intraday underlying bars
- IV surfaces or IV metrics

## Trading Foundation Dataset Mapping

| Requirement | Needed by repo? | Trading Foundation source | Status | Notes |
| ----------- | --------------: | ------------------------- | ------ | ----- |
| Historical underlying daily close for snapshot spot alignment | yes | `historical_data/<TICKER>/eod/<TICKER>_1D.csv` | `PASS` | Adapter can join same-day `close` when raw snapshot rows do not carry `underlying_price`. |
| Once-per-day historical option opportunity-set snapshot | yes | `historical_data/<TICKER>/option_snapshot/<TICKER>_options_snapshot_YYYY-MM-DD.csv` | `PASS WITH LIMITATIONS` | New adapter writes strict manifest metadata and reuses the repo's existing historical scan. Raw Trading Foundation fields map through `option_symbol`, `bid_price`, `ask_price`, and `implied_volatility`. |
| Historical option OHLC path information | no | `historical_data/<TICKER>/option_ohlc/option_ohlc_YYYY-MM-DD.csv` | `PASS` | Not required because the repo does not yet simulate exits or contract lifecycle PnL. |
| One-minute underlying bars | no | `historical_data/<TICKER>/intraday/<TICKER>_YYYY-MM-DD_1min.csv` | `PASS` | Not required for the maintained daily snapshot and expiration-close workflow. |
| IV surfaces / IV metrics / IV ranks | no | `historical_data/<TICKER>/volatility/*` | `PASS` | The scanner uses per-contract IV from the snapshot rows it scans. |
| Broad date coverage across real main-machine historical folders | yes | `option_snapshot/` plus `eod/` folder inventory | `UNKNOWN — MAIN-MACHINE COVERAGE AUDIT REQUIRED` | The sandbox copy includes Trading Foundation loaders and schema summary, but not populated `option_snapshot/` and `eod/` folders for direct coverage measurement. |

## Exact Fields Required

Fields the scanner actually needs from the historical option opportunity-set layer:

- `option_symbol`
- `expiration` or `expiration_date`
- `strike` or `strike_price`
- `type` or `option_type`
- `bid` or `bid_price`
- `ask` or `ask_price`
- `implied_vol` or `implied_volatility`
- one consistent `underlying_price` for the snapshot
- snapshot provenance: `snapshot_id`, `snapshot_source`, `quote_observed_at`, `underlying_price_observed_at`, `underlying_price_source`

Fields used optionally but not strictly required by the maintained scanner:

- `delta`
- `bid_size`
- `ask_size`
- other Greeks

Fields the realized-outcome materialization path actually needs from the underlying daily layer:

- `close`
- `t`
- `symbol`

## Temporal Granularity

The maintained repo path currently requires:

- `once-per-day point-in-time chain snapshot`
- `daily underlying close`
- `expiration observation`

It does **not** currently require:

- `one-minute option OHLC`
- `multiple intraday chain snapshots`
- `event-time quote`
- `full contract lifecycle`

Important limitation:

- the inspected Trading Foundation sandbox schema summary shows no guaranteed uniform snapshot-level timestamp column in `option_snapshot/`
- when the raw snapshot file lacks one explicit shared snapshot timestamp, the new adapter emits `quote_observed_at` and `underlying_price_observed_at` as **day-precision** markers derived from the snapshot date
- that is acceptable for the repo's current daily opportunity-set research, but it is **not** an intraday event-time contract

## Historical Depth

Minimum functional integration:

- one or more dated `option_snapshot` files
- matching `eod` coverage for the snapshot date and expiration date(s)

Research sample size needed for stronger conclusions:

- enough dated snapshots to create a meaningful prediction/outcome panel
- enough expiration groups to evaluate calibration behavior
- real main-machine folder coverage must still be audited before drawing broader conclusions

## Existing Repo Functionality Reused

The Trading Foundation integration deliberately reuses the repo's existing maintained components:

- `options_edge_scanner.data.loader.load_option_quotes(...)`
- `options_edge_scanner.data.historical_snapshot_loader.load_historical_snapshots(...)`
- `options_edge_scanner.cli.historical_snapshot_scan`
- `options_edge_scanner.calibration.materialization.materialize_realized_outcomes_from_snapshot_manifest(...)`
- `options_edge_scanner.data.realized_underlying` contract validation and CSV writer

## Code Added

New adapter capabilities:

- `options_edge_scanner.data.trading_foundation`
- `python -m options_edge_scanner.cli.trading_foundation_snapshot_manifest`
- `python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export`

Supporting loader upgrade:

- `load_option_quotes(...)` now understands Trading Foundation `bid_price` / `ask_price` aliases
- `load_option_quotes(...)` now parses OCC-style `option_symbol` values to recover ticker, expiration, strike, and call/put type when raw files omit explicit normalized columns

## Tests Updated

Targeted validation added:

- `tests/test_trading_foundation_integration.py`

Covered behaviors:

- Trading Foundation price alias mapping plus OCC `option_symbol` parsing
- strict manifest and metadata generation against raw Trading Foundation snapshot files
- end-to-end historical scan plus realized-outcome materialization from canonical `option_snapshot/` and `eod/`-shaped fixtures

## Sandbox Validation Result

Validated in the sandbox on Sunday, August 23, 2026:

- `pytest -q tests/test_trading_foundation_integration.py`
- `python -m compileall options_edge_scanner`

Observed sandbox limitation:

- `C:\GitHub\Trading_Foundation\historical_data\SPY` in the sandbox contains `schema_summary.json`, but not populated `option_snapshot/` or `eod/` folders
- therefore schema integration is validated, but production coverage is still a main-machine question

## Main-Machine Validation Package

Run this exact sequence on the main machine after pulling the updated repo:

1. Build the strict manifest from canonical Trading Foundation snapshots.

```powershell
python -m options_edge_scanner.cli.trading_foundation_snapshot_manifest `
  --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data `
  --ticker SPY `
  --start-date 2025-05-27 `
  --end-date 2025-05-30 `
  --manifest-output outputs\trading_foundation\spy_manifest.csv
```

2. Run the maintained historical scanner.

```powershell
python -m options_edge_scanner.cli.historical_snapshot_scan `
  --manifest outputs\trading_foundation\spy_manifest.csv `
  --output outputs\trading_foundation\spy_candidates.csv `
  --summary-output outputs\trading_foundation\spy_summary.csv
```

3. Export normalized realized-underlying rows from canonical Trading Foundation EOD files.

```powershell
python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export `
  --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data `
  --ticker SPY `
  --start 2025-06-20 `
  --end 2025-07-18 `
  --output outputs\realized_underlying\spy_expiration_day_close_tf.csv
```

4. Materialize realized outcomes from the strict manifest and normalized underlying artifact.

```powershell
python -m options_edge_scanner.cli.materialize_realized_outcomes `
  --manifest outputs\trading_foundation\spy_manifest.csv `
  --realized-underlying outputs\realized_underlying\spy_expiration_day_close_tf.csv `
  --output outputs\trading_foundation\spy_realized_outcomes.csv
```

5. Export predictions from the historical scan output.

```powershell
python -m options_edge_scanner.cli.export_probability_predictions `
  --opportunities outputs\trading_foundation\spy_candidates.csv `
  --output outputs\trading_foundation\spy_predictions.csv
```

6. Evaluate calibration if the selected snapshot window produces prediction/outcome overlap.

```powershell
python -m options_edge_scanner.cli.probability_calibration_eval `
  --predictions outputs\trading_foundation\spy_predictions.csv `
  --outcomes outputs\trading_foundation\spy_realized_outcomes.csv `
  --summary-output outputs\trading_foundation\spy_calibration_summary.csv `
  --bins-output outputs\trading_foundation\spy_calibration_bins.csv `
  --observations-output outputs\trading_foundation\spy_calibration_observations.csv
```

Expected output files:

- `outputs\trading_foundation\spy_manifest.csv`
- `outputs\trading_foundation\spy_manifest_metadata\*.meta.json`
- `outputs\trading_foundation\spy_candidates.csv`
- `outputs\trading_foundation\spy_summary.csv`
- `outputs\realized_underlying\spy_expiration_day_close_tf.csv`
- `outputs\trading_foundation\spy_realized_outcomes.csv`
- `outputs\trading_foundation\spy_predictions.csv`
- optional calibration outputs if enough overlap exists

Main-machine sanity checks:

- `spy_summary.csv` should show `status=success` for the selected rows
- `spy_candidates.csv` should carry `snapshot_id`, `quote_observed_at`, `underlying_price_observed_at`, `input_path`, and `source_metadata_path`
- the manifest metadata sidecars should show `quote_observed_at_policy=file_date_day_precision` only when the raw snapshot file lacks a better uniform timestamp
- `spy_expiration_day_close_tf.csv` should contain `source=trading_foundation`, `source_dataset=historical_data.eod`, `price_field=close`, and `source_bar_timestamp`
- `spy_realized_outcomes.csv` should materialize one row per required expiration with no forward-fill warnings or date mismatches

Failure signals to watch for:

- missing `option_snapshot` or `eod` file coverage in the selected date range
- raw snapshot files that cannot be parsed into expiration/strike/type from `option_symbol`
- zero successful manifest rows in `spy_summary.csv`
- empty `spy_candidates.csv` after the scan if the selected snapshots have no spreads that survive current filters
- `materialize_realized_outcomes` errors about missing `required_outcome_key`

Paste back for review:

- the first 10 rows of `outputs\trading_foundation\spy_summary.csv`
- the first 10 rows of `outputs\trading_foundation\spy_candidates.csv`
- the first 10 rows of `outputs\realized_underlying\spy_expiration_day_close_tf.csv`
- the first 10 rows of `outputs\trading_foundation\spy_realized_outcomes.csv`
- any error text if one of the commands fails

## Classification

`READY_WITH_LIMITATIONS_FOR_MAIN_MACHINE_VALIDATION`

Why:

- the repo now has a concrete adapter for the canonical Trading Foundation historical snapshot and EOD substrate
- the maintained scanner and realized-outcome paths can consume that substrate without building a new historical data platform
- the remaining uncertainty is no longer “historical options data is unavailable”
- the remaining uncertainty is specifically:
  - main-machine date coverage
  - day-precision snapshot provenance when no uniform raw snapshot timestamp exists
  - broader research sample size for calibration conclusions
