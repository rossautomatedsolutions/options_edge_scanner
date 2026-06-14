# options_edge_scanner

`options_edge_scanner` is a research-only foundation for studying deterministic vertical spread screening workflows from normalized option-chain data.

## Research Boundary

This repository is for research, educational use, and decision support only.

It does not implement:

- live trading
- order placement
- brokerage integration
- trade alerts
- recommendations
- autonomous signal execution

For a repo-local status summary of the current offline scanner surface, see [docs/offline_scanner_readiness_review.md](/C:/GitHub/options_edge_scanner/docs/offline_scanner_readiness_review.md).
For a concise demo/runbook for the committed offline scan workflow, see [docs/offline_scanner_demo.md](/C:/GitHub/options_edge_scanner/docs/offline_scanner_demo.md).
For a notebook walkthrough of the same offline workflow, see [notebooks/01_offline_scanner_demo.ipynb](/C:/GitHub/options_edge_scanner/notebooks/01_offline_scanner_demo.ipynb).

## What Is Implemented

- normalized option-chain loading in [options_edge_scanner/data/option_chain_loader.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/data/option_chain_loader.py)
- vertical debit spread generation in [options_edge_scanner/scanner/spread_generator.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/scanner/spread_generator.py)
- probability estimation for canonical vertical spread rows in [options_edge_scanner/models/probability_estimator.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/models/probability_estimator.py)
- expected-value calculation in [options_edge_scanner/models/spread_ev_calculator.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/models/spread_ev_calculator.py)
- deterministic offline scanner orchestration in [options_edge_scanner/scanner/engine.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/scanner/engine.py)
- offline local-file adapter in [options_edge_scanner/data/loader.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/data/loader.py)
- canonical contracts in [docs/data_contracts.md](/C:/GitHub_Review_Folder/options_edge_scanner/docs/data_contracts.md)
- backtest placeholder contracts in [docs/backtest_contracts.md](/C:/GitHub_Review_Folder/options_edge_scanner/docs/backtest_contracts.md)
- offline integration coverage using [tests/fixtures/sample_option_chain.csv](/C:/GitHub_Review_Folder/options_edge_scanner/tests/fixtures/sample_option_chain.csv)

## What Is Not Implemented

- real backtesting workflow
- pricing model calibration
- signal publishing layer
- centralized logging setup
- end-to-end live market runtime

Backtest implementation is not yet implemented. The repo currently defines research-only backtest contracts and sample fixtures, and [options_edge_scanner/backtest/runner.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/backtest/runner.py) now provides a minimal contract adapter only. It returns placeholder-shaped trade-result and summary dataframes for downstream development, and now isolates placeholder accounting hooks for realized PnL, outcome labeling, and exit labeling. These hooks are intentionally non-economic for now and do not implement real historical fills, exit rules, or pricing.
Exit fixtures are now contract-defined for future offline deterministic tests, but they are not yet used by the runner.
They can now be loaded and validated through opt-in helpers, still without any real historical pricing or execution modeling.

The current remaining stubs are:

- [options_edge_scanner/models/pricing.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/models/pricing.py)
- [options_edge_scanner/signals/generator.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/signals/generator.py)
- [options_edge_scanner/utils/logger.py](/C:/GitHub_Review_Folder/options_edge_scanner/options_edge_scanner/utils/logger.py)

## Offline Adapter Usage

Use the offline adapter to load local contract-compliant quote files and feed the deterministic scanner path:

```python
from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities

option_quotes = load_option_quotes("tests/fixtures/sample_option_chain.csv")
opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")
```

Supported input formats:

- `.csv`
- `.parquet` when pandas parquet support is already installed

The adapter validates the `OptionQuoteRow` contract and does not fetch live data.

## Offline Scan Entrypoint

Run the research-only offline scan entrypoint to turn a local `OptionQuoteRow` file into a ranked `ScannerOpportunityRow` CSV artifact:

```powershell
python -m options_edge_scanner.cli.offline_scan --input tests/fixtures/sample_option_chain.csv --output outputs/offline_scan_sample.csv --as-of 2026-01-02
```

Notes:

- this path is offline only and does not fetch live data
- input must be a local contract-compliant `.csv` or `.parquet` file
- input should include `underlying_price`; when it does not, provide `--spot`
- output is a CSV artifact such as `outputs/offline_scan_sample.csv`
- this workflow is for research, education, and decision support only
- deterministic fixture runs should use an explicit `--as-of` date
- conservative quality guardrails are enabled by default for demo/research realism:
- `--max-abs-moneyness-pct 0.25`
- `--max-debit-fraction 0.67`
- `--max-bid-ask-spread-pct 0.25`
- optional `--min-volume`, `--min-open-interest`, `--min-abs-delta`, and `--max-abs-delta` filters are only applied when those columns exist in the local file

Example with an explicit spot override:

```powershell
python -m options_edge_scanner.cli.offline_scan --input tests/fixtures/sample_option_chain.csv --output outputs/offline_scan_sample.csv --as-of 2026-01-02 --spot 100
```

For an end-to-end PowerShell demo flow, including output preview and grouping commands, see [docs/offline_scanner_demo.md](/C:/GitHub/options_edge_scanner/docs/offline_scanner_demo.md).
For a blog/demo-friendly notebook version of the workflow, see [notebooks/01_offline_scanner_demo.ipynb](/C:/GitHub/options_edge_scanner/notebooks/01_offline_scanner_demo.ipynb).

## Offline Batch Manifest

Run the research-only batch entrypoint to scan multiple local quote files from a manifest:

```powershell
python -m options_edge_scanner.cli.offline_batch_scan --manifest tests/fixtures/offline_scan_manifest.csv --summary-output outputs/offline_batch_summary.csv
```

Minimal CSV manifest format:

```csv
input_path,output_path,as_of
tests/fixtures/sample_option_chain.csv,outputs/offline_batch_scan_sample.csv,2026-01-02
```

Notes:

- this path is offline only and does not fetch live data
- each manifest row should provide an explicit `as_of` date for deterministic historical fixture runs
- output artifacts are ranked `ScannerOpportunityRow` CSV files written to each row's `output_path`
- an optional summary artifact such as `outputs/offline_batch_summary.csv` can capture per-row status and row counts
- this workflow is for research, education, and decision support only

Summary CSV contract:

```csv
input_path,output_path,as_of,status,row_count,error_message
tests/fixtures/sample_option_chain.csv,outputs/offline_batch_scan_sample.csv,2026-01-02,success,9,
```

Summary rules:

- successful rows use `status=success`, the produced scanner row count, and a blank `error_message`
- failed rows use `status=failed`, `row_count=0`, and a concise error message
- default batch behavior is fail-fast
- use `--continue-on-error` to keep processing later rows and record failures in the summary

## Deterministic Validation

Run:

```powershell
$env:PYTHONPATH='.'; pytest -q
python -m compileall options_edge_scanner run_scanner.py
python -m options_edge_scanner.cli.offline_scan --input tests/fixtures/sample_option_chain.csv --output outputs/offline_scan_sample.csv --as-of 2026-01-02
python -m options_edge_scanner.cli.offline_batch_scan --manifest tests/fixtures/offline_scan_manifest.csv --summary-output outputs/offline_batch_summary.csv
```

The integration test is fully offline and does not depend on `yfinance`.
