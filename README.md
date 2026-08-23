# options_edge_scanner

`options_edge_scanner` is a research-only offline foundation for studying deterministic vertical spread screening from local option-chain snapshots.

## Research Boundary

This repository is for research, education, and decision support only.

It does not implement:

- live trading
- order placement
- brokerage integration
- trade alerts
- recommendations
- autonomous signal execution
- historical option lifecycle replay

Current repo-local status is summarized in [docs/offline_scanner_readiness_review.md](docs/offline_scanner_readiness_review.md).
The latest offline gap audit and main-machine gate live in [docs/offline_gap_audit_2026-08-17.md](docs/offline_gap_audit_2026-08-17.md).
The maintained demo/runbook lives in [docs/offline_scanner_demo.md](docs/offline_scanner_demo.md).
The notebook walkthrough lives in [notebooks/01_offline_scanner_demo.ipynb](notebooks/01_offline_scanner_demo.ipynb).
The current Trading Foundation historical-data integration status lives in [docs/HISTORICAL_OPTIONS_DATA_STATUS.md](docs/HISTORICAL_OPTIONS_DATA_STATUS.md).

## What Is Implemented

- local-file option quote loading and validation in [options_edge_scanner/data/loader.py](options_edge_scanner/data/loader.py)
- point-in-time provenance enrichment and validation in [options_edge_scanner/data/provenance.py](options_edge_scanner/data/provenance.py)
- debit vertical spread generation in [options_edge_scanner/scanner/spread_generator.py](options_edge_scanner/scanner/spread_generator.py)
- per-spread execution-aware entry adjustments and liquidity diagnostics in [options_edge_scanner/scanner/execution.py](options_edge_scanner/scanner/execution.py)
- probability-of-profit estimation from spread breakevens in [options_edge_scanner/models/probability_estimator.py](options_edge_scanner/models/probability_estimator.py)
- versioned probability-model wrappers and explicit predicted-event metadata in [options_edge_scanner/models/probability_models.py](options_edge_scanner/models/probability_models.py)
- exact expected-value calculation for scanner-supported debit verticals under the repo's current lognormal assumption in [options_edge_scanner/models/spread_ev_calculator.py](options_edge_scanner/models/spread_ev_calculator.py)
- deterministic offline scanner orchestration, config-driven `run_scan(...)`, and row-count diagnostics in [options_edge_scanner/scanner/engine.py](options_edge_scanner/scanner/engine.py)
- ranking-score selection and optional concentration caps in [options_edge_scanner/scanner/opportunity_ranker.py](options_edge_scanner/scanner/opportunity_ranker.py)
- machine-readable JSON scan reports in [options_edge_scanner/scanner/reporting.py](options_edge_scanner/scanner/reporting.py)
- offline single-run and batch CLIs in [options_edge_scanner/cli/offline_scan.py](options_edge_scanner/cli/offline_scan.py) and [options_edge_scanner/cli/offline_batch_scan.py](options_edge_scanner/cli/offline_batch_scan.py)
- strict historical snapshot manifests, loaders, and multi-snapshot scanning in [options_edge_scanner/data/historical_snapshot_loader.py](options_edge_scanner/data/historical_snapshot_loader.py) and [options_edge_scanner/cli/historical_snapshot_scan.py](options_edge_scanner/cli/historical_snapshot_scan.py)
- canonical Trading Foundation manifest/metadata generation against raw `historical_data/<TICKER>/option_snapshot/*.csv` files in [options_edge_scanner/data/trading_foundation.py](options_edge_scanner/data/trading_foundation.py) and [options_edge_scanner/cli/trading_foundation_snapshot_manifest.py](options_edge_scanner/cli/trading_foundation_snapshot_manifest.py)
- research-only probability calibration contracts, prediction export, forward-only evaluation helpers, and offline CLIs in [options_edge_scanner/calibration](options_edge_scanner/calibration), [options_edge_scanner/cli/export_probability_predictions.py](options_edge_scanner/cli/export_probability_predictions.py), [options_edge_scanner/cli/probability_calibration_eval.py](options_edge_scanner/cli/probability_calibration_eval.py), and [docs/calibration_contracts.md](docs/calibration_contracts.md)
- explicit SPY expiration-close terminal outcome semantics in [options_edge_scanner/calibration/terminal_semantics.py](options_edge_scanner/calibration/terminal_semantics.py)
- provider-neutral realized underlying contracts and Alpaca historical stock-bar normalization in [options_edge_scanner/data/realized_underlying.py](options_edge_scanner/data/realized_underlying.py), [options_edge_scanner/data/alpaca_historical.py](options_edge_scanner/data/alpaca_historical.py), and [options_edge_scanner/cli/alpaca_realized_underlying_acquire.py](options_edge_scanner/cli/alpaca_realized_underlying_acquire.py)
- canonical Trading Foundation EOD normalization into the same realized-underlying contract in [options_edge_scanner/data/trading_foundation.py](options_edge_scanner/data/trading_foundation.py) and [options_edge_scanner/cli/trading_foundation_realized_underlying_export.py](options_edge_scanner/cli/trading_foundation_realized_underlying_export.py)
- strict realized outcome materialization from historical snapshot manifests plus normalized underlying artifacts in [options_edge_scanner/calibration/materialization.py](options_edge_scanner/calibration/materialization.py) and [options_edge_scanner/cli/materialize_realized_outcomes.py](options_edge_scanner/cli/materialize_realized_outcomes.py)
- optional Yahoo snapshot ingestion with metadata sidecars in [options_edge_scanner/yahoo_ingestion.py](options_edge_scanner/yahoo_ingestion.py)
- contract and fixture coverage in [docs/data_contracts.md](docs/data_contracts.md) and [tests/fixtures](tests/fixtures)

## What Is Not Implemented

- broad historical option dataset acquisition, normalization, and lifecycle replay
- empirically calibrated probability-model replacement for the current lognormal baseline
- broad historical dataset acquisition and normalization beyond the bounded SPY expiration-close contract
- multi-symbol terminal observation policy coverage beyond the explicit SPY-only rule
- full historical execution simulation, exits, and portfolio replay
- real backtesting workflow
- signal publishing layer
- centralized logging setup
- end-to-end live market runtime

The backtest layer remains a clearly labeled placeholder contract adapter in [options_edge_scanner/backtest/runner.py](options_edge_scanner/backtest/runner.py).

Current remaining stubs:

- [options_edge_scanner/models/pricing.py](options_edge_scanner/models/pricing.py)
- [options_edge_scanner/signals/generator.py](options_edge_scanner/signals/generator.py)
- [options_edge_scanner/utils/logger.py](options_edge_scanner/utils/logger.py)

## Maintained Workflow

The maintained scanner path is offline and local-file driven:

1. Optionally generate a local snapshot with:

```powershell
python -m options_edge_scanner.cli.yahoo_option_chain_ingest --ticker SPY --expiration nearest --output-dir outputs/yahoo_option_chains/SPY --write-raw-json
```

2. Run the offline scanner against a local CSV or parquet file:

```powershell
python -m options_edge_scanner.cli.offline_scan --input tests/fixtures/sample_option_chain.csv --output outputs/offline_scan_sample.csv --report-output outputs/offline_scan_report.json --as-of 2026-01-02
```

The scanner:

- consumes local files only
- derives `mid` from `bid`/`ask` when the raw input omits it
- requires point-in-time quote provenance by default
- rejects `as_of` values that predate the observed snapshot unless `--allow-unsafe-as-of` is passed
- treats date-only `--as-of` values as day-level bounds, while timestamp-valued `as_of` inputs are checked at full timestamp precision
- carries provenance fields into the ranked output
- computes conservative execution-adjusted entry debits alongside quoted midpoint economics
- emits liquidity diagnostics, ranking scores, and selection ranks in the ranked CSV
- can write a machine-readable JSON report describing counts, model metadata, and top rows
- uses conservative quality and ranking filters by default

For strict historical research across multiple dated local snapshots, use the historical manifest path:

```powershell
python -m options_edge_scanner.cli.historical_snapshot_scan --manifest path/to/strict_historical_manifest.csv --output outputs/historical_snapshot_candidates.csv --summary-output outputs/historical_snapshot_summary.csv
```

The historical manifest path:

- resolves `chain_path` and `metadata_path` relative to the manifest file
- requires explicit snapshot identity in both the manifest and the sidecar metadata, plus explicit spot provenance
- rejects snapshots whose quote timestamp and spot timestamp do not match exactly
- preserves snapshot provenance in every candidate row
- emits per-snapshot success/failure accounting
- does not offer an unsafe historical bypass

For canonical Trading Foundation daily historical inputs, first build a strict manifest that points at raw upstream snapshots without copying the chain CSVs:

```powershell
python -m options_edge_scanner.cli.trading_foundation_snapshot_manifest `
  --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data `
  --ticker SPY `
  --snapshot-date 2025-05-27 `
  --snapshot-date 2025-05-28 `
  --manifest-output outputs/trading_foundation/spy_manifest.csv

python -m options_edge_scanner.cli.historical_snapshot_scan `
  --manifest outputs/trading_foundation/spy_manifest.csv `
  --output outputs/trading_foundation/spy_candidates.csv `
  --summary-output outputs/trading_foundation/spy_summary.csv
```

That adapter path:

- reuses the repo's strict manifest contract and existing historical scanner
- parses `option_symbol` plus Trading Foundation `bid_price`/`ask_price` fields into the repo's canonical option-quote shape
- joins same-day Trading Foundation `eod/<TICKER>_1D.csv` close data when the raw snapshot file does not carry a usable `underlying_price`
- emits day-precision `quote_observed_at` metadata when the raw snapshot file lacks one uniform explicit snapshot timestamp

The ad hoc batch manifest path now also resolves `input_path` and `output_path` relative to the manifest file so the same bundle can move between machines without relying on the caller's current working directory.

For SPY expiration-outcome research, the maintained realized-outcome path is now:

```powershell
python -m options_edge_scanner.cli.alpaca_realized_underlying_acquire `
  --ticker SPY `
  --start 2026-06-15 `
  --end 2026-07-17 `
  --timeframe 1Day `
  --adjustment raw `
  --feed sip `
  --output outputs/realized_underlying/spy_expiration_day_close_proxy_raw.csv `
  --write-raw-json

python -m options_edge_scanner.cli.materialize_realized_outcomes `
  --manifest path/to/strict_spy_snapshot_manifest.csv `
  --realized-underlying outputs/realized_underlying/spy_expiration_day_close_proxy_raw.csv `
  --output outputs/realized_outcomes/spy_expiration_outcomes.csv
```

That path is deliberately explicit about:

- SPY-only terminal-price semantics
- explicit date range
- explicit Alpaca timeframe
- explicit feed choice
- explicit adjustment mode, defaulting to `raw`
- refusal to forward-fill or silently roll non-trading-day outcome dates

For canonical Trading Foundation EOD inputs, the maintained local-file alternative is:

```powershell
python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export `
  --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data `
  --ticker SPY `
  --start 2026-06-15 `
  --end 2026-07-17 `
  --output outputs/realized_underlying/spy_expiration_day_close_tf.csv
```

Important boundary:

- the current repo-local Yahoo SPY chain files are useful for expiration inventory, but they are not treated as strict historical snapshot inputs for calibration because their `quote_observed_at` provenance is fetch time rather than a trusted option-quote timestamp
- the canonical Trading Foundation adapter supports daily historical opportunity-set research today, but if raw snapshot files omit a uniform explicit snapshot timestamp it preserves only day-precision snapshot provenance rather than inventing intraday event-time precision

A collection of local snapshots is still not automatically a valid backtest dataset. The repo does not yet model execution, exits, liquidity, survivorship, or portfolio behavior.

If the input file lacks `underlying_price`, pass `--spot`.
If you override spot safely, also pass `--spot-observed-at` and optionally `--spot-source`.
If the input file lacks quote provenance and you intentionally want an unsafe ad hoc run, pass `--allow-unsafe-as-of`.

For calibration export after a safe scan:

```powershell
python -m options_edge_scanner.cli.export_probability_predictions --opportunities outputs/offline_scan_sample.csv --output outputs/offline_scan_predictions.csv
```

## Output Shape

The ranked scanner CSV includes:

- spread structure plus both quoted midpoint and execution-adjusted economics
- `as_of`
- quote and spot provenance fields when available
- versioned probability-model metadata
- exact predicted-event metadata used by the probability field
- probability-of-profit
- execution-adjusted expected value plus theoretical midpoint EV reference
- edge percentage
- liquidity score, entry slippage diagnostics, ranking score, and selection rank
- `ev_method`
- conditional average profit and loss under the current EV method

The optional JSON report artifact includes deterministic row counts, active execution/selection assumptions, model/version metadata, and the top ranked rows.

Safe scanner outputs can be projected into the calibration prediction contract through `python -m options_edge_scanner.cli.export_probability_predictions` or `options_edge_scanner.calibration.export_scanner_probability_predictions(...)`.
Those prediction artifacts are evaluated against separate realized-outcome artifacts by [options_edge_scanner/cli/probability_calibration_eval.py](options_edge_scanner/cli/probability_calibration_eval.py).
The realized-outcome artifacts themselves can now be materialized from strict historical snapshot manifests plus normalized underlying observations.

See [docs/data_contracts.md](docs/data_contracts.md) for the scanner/dataframe contracts and [docs/calibration_contracts.md](docs/calibration_contracts.md) for the calibration workflow.

## Legacy Path

[run_scanner.py](run_scanner.py) is intentionally retired.
It now redirects callers to the maintained offline workflow because the old live-data prototype used a separate spread/EV stack and did not enforce current provenance checks.

## Deterministic Validation

Run:

```powershell
pytest -q
python -m compileall options_edge_scanner run_scanner.py
python -m options_edge_scanner.cli.offline_scan --input tests/fixtures/sample_option_chain.csv --output outputs/offline_scan_sample.csv --report-output outputs/offline_scan_report.json --as-of 2026-01-02
python -m options_edge_scanner.cli.offline_batch_scan --manifest tests/fixtures/offline_scan_manifest.csv --summary-output outputs/offline_batch_summary.csv
python -m options_edge_scanner.cli.historical_snapshot_scan --manifest path/to/strict_historical_manifest.csv --output outputs/historical_snapshot_candidates.csv --summary-output outputs/historical_snapshot_summary.csv
python -m options_edge_scanner.cli.trading_foundation_snapshot_manifest --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data --ticker SPY --snapshot-date 2025-05-27 --manifest-output outputs/trading_foundation/spy_manifest.csv
python -m options_edge_scanner.cli.export_probability_predictions --opportunities outputs/offline_scan_sample.csv --output outputs/offline_scan_predictions.csv
python -m options_edge_scanner.cli.alpaca_realized_underlying_acquire --ticker SPY --start 2026-06-15 --end 2026-07-17 --timeframe 1Day --adjustment raw --feed sip --output outputs/realized_underlying/spy_expiration_day_close_proxy_raw.csv
python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export --historical-data-root C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data --ticker SPY --start 2026-06-15 --end 2026-07-17 --output outputs/realized_underlying/spy_expiration_day_close_tf.csv
python -m options_edge_scanner.cli.materialize_realized_outcomes --manifest path/to/strict_spy_snapshot_manifest.csv --realized-underlying outputs/realized_underlying/spy_expiration_day_close_proxy_raw.csv --output outputs/realized_outcomes/spy_expiration_outcomes.csv
python -m options_edge_scanner.cli.probability_calibration_eval --predictions tests/fixtures/sample_probability_predictions.csv --outcomes tests/fixtures/sample_realized_outcomes.csv --summary-output outputs/calibration_summary.csv --bins-output outputs/calibration_bins.csv --observations-output outputs/calibration_observations.csv
```

The scanner and tests are offline.
The optional Yahoo ingestion command requires network access and the `yfinance` dependency, and the optional Alpaca realized-underlying acquisition command requires Alpaca credentials plus market-data access, but the scanner itself does not fetch market data at runtime.
