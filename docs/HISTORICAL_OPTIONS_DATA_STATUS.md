# Historical Options Data Status

Date: Monday, August 24, 2026
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

## Code Added / Updated

New adapter capabilities:

- `options_edge_scanner.data.trading_foundation`
- `python -m options_edge_scanner.cli.trading_foundation_snapshot_manifest`
- `python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export`

Supporting loader upgrade:

- `load_option_quotes(...)` now understands Trading Foundation `bid_price` / `ask_price` aliases
- `load_option_quotes(...)` now parses OCC-style `option_symbol` values to recover ticker, expiration, strike, and call/put type when raw files omit explicit normalized columns

Historical-validation hardening added on Sunday, August 23, 2026 and extended on Monday, August 24, 2026:

- quote and spread quality filters now reject non-finite Trading Foundation numeric inputs such as missing IV before they can poison otherwise usable snapshots
- the probability and EV layers now require finite positive spot, strike, IV, and time-to-expiration inputs instead of propagating `NaN` values into `Estimated probability must be finite`
- realized-underlying export can now derive exact required expiration dates directly from a strict snapshot manifest via `--manifest`
- realized-outcome materialization now partitions already-realized versus future expirations using `--realized-as-of`, so future-dated contracts after Sunday, August 23, 2026 no longer fail historical calibration materialization
- Trading Foundation EOD export now emits per-date coverage audit details so missing dates can be classified as absent trading days versus rows dropped for invalid `close`/`t` values

## Tests Updated

Targeted validation added:

- `tests/test_trading_foundation_integration.py`
- `tests/test_realized_outcome_materialization.py`

Covered behaviors:

- Trading Foundation price alias mapping plus OCC `option_symbol` parsing
- strict manifest and metadata generation against raw Trading Foundation snapshot files
- end-to-end historical scan plus realized-outcome materialization from canonical `option_snapshot/` and `eod/`-shaped fixtures
- Trading Foundation-shaped snapshots with one non-finite IV contract now skip the bad contract without failing the whole snapshot
- manifest-driven Trading Foundation realized-underlying export emits only already-realized expiration dates as of Sunday, August 23, 2026
- realized-outcome materialization excludes future expirations instead of treating them as missing realized-underlying observations
- Trading Foundation EOD coverage audits distinguish `trading_day_absent_from_canonical_eod` from `raw_row_present_but_invalid_close_or_timestamp`
- June 18, 2026 is explicitly validated as an acceptable SPY expiration outcome date under the current policy even though Friday, June 19, 2026 is the Juneteenth market holiday

## Sandbox Validation Result

Validated in the sandbox on Monday, August 24, 2026:

- `pytest -q tests/test_trading_foundation_integration.py`: `7 passed`
- `pytest -q tests/test_realized_outcome_materialization.py`: `6 passed`
- `pytest -q tests/test_realized_underlying.py`: `12 passed`
- `pytest -q`: `161 passed`
- `python -m compileall options_edge_scanner run_scanner.py`: passed

Observed sandbox limitation:

- `C:\GitHub\Trading_Foundation\historical_data\SPY` in the sandbox contains `schema_summary.json`, but not populated `option_snapshot/` or `eod/` folders
- `C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data` does not exist in this environment, so the real May 27, 2025 through May 30, 2025 rerun still has to happen on the actual main machine where the canonical store is mounted
- therefore schema integration and the code fix are validated locally, but production coverage and the exact May 2025 candidate counts remain a main-machine question

## Main-Machine EOD Audit Finding

The real main-machine validation reported one narrowed Trading Foundation EOD blocker for manifest-derived SPY expiration outcomes as of the explicit cutoff `2026-08-23T12:00:00Z`:

- missing realized event dates: `2025-07-11`, `2025-07-18`, `2026-06-18`

Current audit interpretation:

- `2025-07-11`: regular Friday trading day, valid SPY weekly expiration candidate, not a market-calendar edge case
- `2025-07-18`: regular Friday trading day, valid SPY standard monthly expiration date, not a market-calendar edge case
- `2026-06-18`: regular Thursday trading day immediately preceding the Friday, June 19, 2026 Juneteenth holiday; this is consistent with the existing weekly-options holiday convention that end-of-week ETF series expire on Thursday when Friday is a holiday

Implication:

- if these dates are not present in canonical `eod/SPY_1D.csv`, the remaining blocker is upstream Trading Foundation EOD coverage or ingestion rather than an Options Edge Scanner expiration-roll rule
- if a raw `SPY_1D.csv` row exists for one of those dates but is dropped because `close` or `t` is invalid, the remaining blocker is still upstream data quality rather than a silent calendar roll inside this repo
- no forward-fill or arbitrary last-trading-session roll has been added in this repo

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

3. Export normalized realized-underlying rows from canonical Trading Foundation EOD files using the strict manifest itself as the required-expiration source.

```powershell
python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export `
  --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data `
  --ticker SPY `
  --manifest outputs\trading_foundation\spy_manifest.csv `
  --realized-as-of 2026-08-23T12:00:00Z `
  --output outputs\trading_foundation\spy_realized_underlying.csv
```

4. Materialize realized outcomes from the strict manifest and normalized underlying artifact, excluding future expirations after Sunday, August 23, 2026.

```powershell
python -m options_edge_scanner.cli.materialize_realized_outcomes `
  --manifest outputs\trading_foundation\spy_manifest.csv `
  --realized-underlying outputs\trading_foundation\spy_realized_underlying.csv `
  --realized-as-of 2026-08-23T12:00:00Z `
  --output outputs\trading_foundation\spy_realized_outcomes.csv
```

5. Export predictions from the historical scan output.

```powershell
python -m options_edge_scanner.cli.export_probability_predictions `
  --opportunities outputs\trading_foundation\spy_candidates.csv `
  --output outputs\trading_foundation\spy_predictions.csv
```

6. Evaluate calibration if the selected snapshot window produces prediction/outcome overlap. Because scanner opportunities can share the same expiration outcome, allow shared outcome keys intentionally.

```powershell
python -m options_edge_scanner.cli.probability_calibration_eval `
  --predictions outputs\trading_foundation\spy_predictions.csv `
  --outcomes outputs\trading_foundation\spy_realized_outcomes.csv `
  --summary-output outputs\trading_foundation\spy_calibration_summary.csv `
  --bins-output outputs\trading_foundation\spy_calibration_bins.csv `
  --observations-output outputs\trading_foundation\spy_calibration_observations.csv `
  --allow-shared-outcome-keys
```

Expected output files:

- `outputs\trading_foundation\spy_manifest.csv`
- `outputs\trading_foundation\spy_manifest_metadata\*.meta.json`
- `outputs\trading_foundation\spy_candidates.csv`
- `outputs\trading_foundation\spy_summary.csv`
- `outputs\trading_foundation\spy_realized_underlying.csv`
- `outputs\trading_foundation\spy_realized_outcomes.csv`
- `outputs\trading_foundation\spy_predictions.csv`
- optional calibration outputs if enough overlap exists

Main-machine sanity checks:

- `spy_summary.csv` should show `status=success` for the selected rows
- `spy_candidates.csv` should carry `snapshot_id`, `quote_observed_at`, `underlying_price_observed_at`, `input_path`, and `source_metadata_path`
- the manifest metadata sidecars should show `quote_observed_at_policy=file_date_day_precision` only when the raw snapshot file lacks a better uniform timestamp
- `spy_realized_underlying.csv` should contain `source=trading_foundation`, `source_dataset=historical_data.eod`, `price_field=close`, and `source_bar_timestamp`
- the realized-underlying export should cover exact required historical expiration dates from the manifest rather than a guessed continuous range
- `spy_realized_outcomes.csv` should print non-zero `future_required_outcome_groups_excluded` whenever the manifest still contains expirations after Sunday, August 23, 2026
- `spy_realized_outcomes.csv` should materialize only already-realized expiration rows with no forward-fill warnings or date mismatches

Failure signals to watch for:

- missing `option_snapshot` or `eod` file coverage in the selected date range
- a canonical-root path that does not actually exist on the machine running the commands
- raw snapshot files that cannot be parsed into expiration/strike/type from `option_symbol`
- zero successful manifest rows in `spy_summary.csv`
- empty `spy_candidates.csv` after the scan if the selected snapshots have no spreads that survive current filters
- `Trading Foundation EOD coverage is missing realized event dates: ...`
- `materialize_realized_outcomes` errors about missing `required_outcome_key` for dates that should already have occurred

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
