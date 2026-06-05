# Offline Scanner Readiness Review

## Current Repo State

- Canonical local clone: `C:\GitHub\options_edge_scanner`
- Remote: `https://github.com/rossautomatedsolutions/options_edge_scanner.git`
- Reviewed synced tip: `2bfd75b Ignore generated offline scanner outputs and clarify offline CLI docs`
- Offline scanner feature commit present locally: `8d7b5c9 Add offline scanner pipeline CLI fixtures`

This review is repo-local and reflects the committed offline scanner surface currently on `main`.

## What The Offline Scanner CLI Currently Does

- Loads local option quote files through `options_edge_scanner.data.loader.load_option_quotes(...)`
- Normalizes and validates quote rows against the `OptionQuoteRow` contract
- Generates same-expiration debit vertical spreads through `generate_vertical_spreads(...)`
- Scores each spread with probability-of-profit and expected-value helpers already in the repo
- Ranks opportunities deterministically through `build_scanner_opportunities(...)`
- Writes ranked scanner output to a caller-specified CSV path
- Supports both single-run CLI execution and batch-manifest execution
- Supports optional deterministic `as_of` dates for fixture-driven runs

Current CLI entrypoints:

- `python -m options_edge_scanner.cli.offline_scan`
- `python -m options_edge_scanner.cli.offline_batch_scan`

## Input Contract Summary

The offline scanner accepts local `.csv` files, and `.parquet` files when pandas parquet support is already installed.

Required normalized quote columns:

- `ticker`
- `expiration`
- `strike`
- `type`
- `bid`
- `ask`
- `mid`
- `implied_vol`
- `underlying_price`

Supported safe aliases currently include:

- `option_type -> type`
- `expiry`, `expiry_date`, `expiration_date -> expiration`
- `strike_price -> strike`
- `iv`, `implied_volatility -> implied_vol`

Batch manifest contract:

- `input_path`
- `output_path`
- `as_of`

## Output Contract Summary

The scanner emits ranked `ScannerOpportunityRow` CSV output with canonical columns including:

- spread identity: `ticker`, `expiration`, `option_type`, `spread_type`
- structure: `lower_strike`, `upper_strike`, `long_strike`, `short_strike`, `width`
- economics: `debit`, `cost`, `max_profit`, `max_loss`
- inputs carried forward: `underlying_price`, `implied_volatility`
- ranking fields: `days_to_expiration`, `probability_of_profit`, `probability`, `prob_loss`, `expected_value`, `EV`, `edge_pct`, `ev_method`, `avg_profit`, `avg_loss`

Batch mode can also emit a summary CSV with:

- `input_path`
- `output_path`
- `as_of`
- `status`
- `row_count`
- `error_message`

## Test Coverage Summary

Current repo tests cover:

- local file loading and contract validation
- missing required input-column failure behavior
- deterministic single-run CLI output writing
- deterministic batch CLI output writing
- optional batch summary generation
- fail-fast manifest validation behavior
- `--continue-on-error` summary behavior
- deterministic pipeline ordering and expected top-row values from fixture input

Fixture coverage is small and stable:

- `tests/fixtures/sample_option_chain.csv`
- `tests/fixtures/offline_scan_manifest.csv`

## Research/Offline Safety Boundary

The current offline scanner surface preserves a research-only boundary:

- local-file input only
- deterministic fixture-friendly execution
- no live market data fetching
- no broker integration
- no order placement
- no order routing
- no autonomous execution behavior
- no recommendation language in the CLI contracts or output schema

The current output is a ranked research artifact, not a trade instruction or brokerage action.

## Known Limitations

- The single-run CLI defaults `as_of` to the current UTC-normalized date when not supplied, so strictly deterministic historical runs should always pass `--as-of`.
- Input coverage is currently centered on a small fixture-driven quote schema rather than a broader family of vendor file formats.
- Batch manifest paths are treated as local filesystem paths and are not normalized relative to the manifest file location.
- The current implementation writes CSV artifacts but does not provide richer reporting, logging, or metadata packaging.
- The current spread generator only covers debit verticals and currently filters widths above 10 strike points.
- The scanner remains a local research workflow and is not a production runtime.

## Recommended Next Steps

Safest next implementation/documentation steps:

1. Add a small CLI behavior note or test that explicitly documents the non-deterministic default when `--as-of` is omitted.
2. Add one or two fixture tests for safe input aliases such as `option_type`, `expiry`, and `iv` so the loader contract is protected by tests, not just implementation.
3. Add a small manifest-path note or test clarifying that manifest row paths are interpreted as local paths exactly as provided.
4. Keep future scanner expansion focused on offline contract coverage before introducing broader workflow plumbing.

## Explicit Non-Goals

- no broker integration
- no live trading
- no order routing
- no recommendation language
- no live market data fetching
