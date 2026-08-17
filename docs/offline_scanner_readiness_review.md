# Offline Scanner Readiness Review

Date: August 17, 2026

## Current Repo State

- Canonical local clone: `C:\GitHub\options_edge_scanner`
- Remote: `https://github.com/rossautomatedsolutions/options_edge_scanner.git`
- Reviewed base commit: `dccee93 Add offline scanner demo notebook`
- This note reflects the current repo-local working tree on top of that base commit.

This document supersedes the older June 2026 offline readiness snapshots for day-to-day repo status.

## What The Maintained Offline Scanner Does Now

- loads local option quote files through `options_edge_scanner.data.loader.load_option_quotes(...)`
- derives `mid` from `bid`/`ask` when a local artifact omits it
- enriches quote provenance from in-file columns or a sibling `.meta.json` sidecar
- validates point-in-time integrity before ranking
- generates same-expiration debit vertical spreads through `generate_vertical_spreads(...)`
- computes conservative execution-adjusted entry economics and per-spread liquidity diagnostics from quoted leg markets when available
- estimates probability of profit from spread breakevens
- preserves explicit probability-model versioning and predicted-event semantics in ranked output
- computes both midpoint-theoretical EV and execution-adjusted EV for scanner-supported debit verticals under the repo's current lognormal terminal-price assumption
- ranks opportunities deterministically through `build_scanner_opportunities(...)`
- writes ranked scanner output to a caller-specified CSV path
- can emit a machine-readable JSON report artifact for single-run scans
- can export safe scanner outputs into separate calibration prediction artifacts through a maintained CLI and evaluate them against separate realized-outcome artifacts
- supports single-run CLI execution, manifest-driven batch execution, and strict historical snapshot-manifest execution

Maintained CLI entrypoints:

- `python -m options_edge_scanner.cli.offline_scan`
- `python -m options_edge_scanner.cli.offline_batch_scan`
- `python -m options_edge_scanner.cli.historical_snapshot_scan`
- `python -m options_edge_scanner.cli.export_probability_predictions`
- `python -m options_edge_scanner.cli.yahoo_option_chain_ingest` as an optional upstream artifact generator only

## Current Safety and Provenance Posture

The maintained offline scanner surface now enforces a stricter research boundary:

- local-file scanner input only
- point-in-time quote provenance required by default
- `as_of` cannot predate the observed snapshot unless `--allow-unsafe-as-of` is passed
- date-only `as_of` values behave as day-level bounds, while timestamp-valued inputs are checked at full timestamp precision
- provenance fields are carried into ranked output
- the strict historical manifest path requires explicit snapshot identity plus explicit spot provenance
- the strict historical manifest path rejects any snapshot where `quote_observed_at` and `underlying_price_observed_at` do not match exactly
- historical manifest artifact paths resolve relative to the manifest file, not the caller's current working directory
- the maintained batch manifest path now also resolves input/output artifact paths relative to the manifest file
- no broker integration
- no order placement
- no order routing
- no autonomous execution behavior
- no recommendation language in the CLI contracts or output schema

The current output is a ranked research artifact, not a trade instruction or brokerage action.

## What Changed Materially

- `expected_value` is no longer the optimistic binary max-profit/max-loss approximation for the maintained debit scanner path
- raw input artifacts no longer need to provide `mid` explicitly when `bid` and `ask` are present
- ranked output now includes `as_of`, quote provenance, and spot provenance fields when available
- ranked output now preserves both quoted midpoint economics and execution-adjusted economics, plus liquidity diagnostics and selection rank
- explicit `--spot` overrides no longer leave stale inherited spot provenance in the emitted output
- the maintained batch manifest path now resolves artifact paths relative to the manifest file for more portable handoff
- strict historical snapshot manifests now bind one logical chain artifact, one metadata sidecar, one timestamped spot reference, and one snapshot ID into a reusable loader/API
- strict historical multi-snapshot scans now preserve per-snapshot failure accounting instead of silently dropping bad rows
- the scanner output now carries exact probability-model versioning and predicted-event metadata needed for downstream calibration
- the repo now includes a maintained prediction-export CLI for calibration handoff
- the repo now includes an optional machine-readable scan report artifact for offline auditability
- the repo now includes explicit prediction/outcome calibration contracts, deterministic reliability metrics, and forward-only evaluation helpers
- the config-driven `run_scan(...)` path now points at the maintained offline contract stack instead of returning an empty frame
- the root `run_scanner.py` entrypoint remains retired because it bypassed the maintained offline contract stack
- the repo test suite now passes via both `python -m pytest -q` and plain `pytest -q`

## Current Test Coverage Summary

Current repo tests cover:

- local file loading and contract validation
- safe alias normalization through a synthetic local option-chain fixture
- `mid` derivation from bid/ask-only local inputs
- missing required input-column failure behavior
- point-in-time rejection when `as_of` predates the observed snapshot
- metadata-sidecar provenance inference
- explicit unsafe override behavior
- deterministic single-run CLI output writing
- optional single-run JSON report output writing
- deterministic batch CLI output writing
- optional batch summary generation
- fail-fast manifest validation behavior
- `--continue-on-error` summary behavior
- batch manifest-relative path resolution for both input and output artifacts
- historical manifest-relative path resolution
- historical duplicate snapshot identity rejection
- historical duplicate metadata-sidecar rejection
- historical same-day intraday snapshot separation
- historical stale-spot rejection
- historical mixed valid/invalid snapshot accounting
- historical zero-candidate snapshot accounting
- deterministic pipeline ordering and expected fixture values under the current execution-adjusted EV method
- maintained prediction-export CLI behavior
- calibration prediction/outcome contract validation
- calibration reliability metrics, safe log loss, and forward-only evaluation windows
- calibration leakage rejection for lookahead outcomes and shared correlated outcomes by default
- retired root-script behavior

Fixture coverage remains small and intentionally stable:

- `tests/fixtures/sample_option_chain.csv`
- `tests/fixtures/offline_scan_manifest.csv`
- `tests/fixtures/sample_option_chain_aliases.csv`

## Known Limitations

- the current baseline probability model still uses a simple lognormal terminal-price assumption; the repo now has evaluation tooling but not an empirically calibrated replacement
- the current execution model is still a conservative heuristic based on quoted width and optional size fields, not a true historical fill simulator
- the exact EV improvement currently applies to the maintained debit scanner path, not to a broader strategy family
- strict historical manifests prevent unsafe chain/spot joins, but the Yahoo path still relies on a separately fetched spot reference rather than a guaranteed same-tick vendor field
- the spread generator still covers debit verticals only and still filters widths above 10 strike points
- the scanner remains a local research workflow and is not a production runtime
- a collection of strict snapshots is still not, by itself, a realistic historical backtest dataset
- the repo-local artifact inventory still does not amount to a meaningful empirical calibration dataset with realized expiration outcomes

## Recommended Next Steps

Safest next implementation priorities after this checkpoint:

1. realized-outcome dataset acquisition and normalization so empirical calibration can actually be measured
2. trusted main-machine point-in-time option-chain acquisition so strict calibration inputs can be generated safely
3. empirically calibrated probability-model experiments only after the prediction/outcome dataset is strong enough
4. richer execution and backtest modeling only after the data and probability layers are stronger

## Explicit Non-Goals

- no broker integration
- no live trading
- no order routing
- no recommendation language
