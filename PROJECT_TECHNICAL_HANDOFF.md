# Project Technical Handoff

Last validated: 2026-08-23
Repository: `C:\GitHub\options_edge_scanner`
Validation basis:

- core package inspection across `options_edge_scanner/`, `docs/`, `tests/`, `notebooks/`, and selected `outputs/`
- recent git history through the current 2026-08-23 Trading Foundation validation hardening changes
- `pytest -q` on 2026-08-23: `158 passed in 19.12s`
- `python -m compileall options_edge_scanner run_scanner.py` on 2026-08-23: passed
- practical artifact checks on 2026-08-17:
  - calibration export from `outputs/historical_snapshots/spy_candidates.csv` succeeded with 40 exported predictions
  - calibration export from `outputs/offline_scan_sample.csv` failed because the artifact is missing current calibration-export columns and `snapshot_id`
  - scanning `outputs/yahoo_option_chains/SPY_2026-06-15_yahoo.csv` failed because the repo-local Yahoo sidecar is missing the now-required `snapshot_id`

## 0. Addendum - Trading Foundation Historical Adapter (2026-08-23)

This addendum updates the historical-options data assessment without changing the 2026-08-17 full-repo validation stamp above.

Targeted validation on Sunday, August 23, 2026:

- `pytest -q tests/test_trading_foundation_integration.py`: `5 passed`
- `pytest -q tests/test_realized_outcome_materialization.py`: `6 passed`
- `pytest -q`: `158 passed`
- `python -m compileall options_edge_scanner run_scanner.py`: passed

New capability added on Sunday, August 23, 2026:

- raw canonical Trading Foundation `historical_data/<TICKER>/option_snapshot/<TICKER>_options_snapshot_YYYY-MM-DD.csv` files can now be consumed through the repo's existing strict historical-manifest path without copying the chain CSVs
- new CLI `python -m options_edge_scanner.cli.trading_foundation_snapshot_manifest` writes manifest rows plus metadata sidecars that point at those raw snapshot files
- new CLI `python -m options_edge_scanner.cli.trading_foundation_realized_underlying_export` normalizes canonical Trading Foundation `eod/<TICKER>_1D.csv` files into the repo's `RealizedUnderlyingObservationRow` contract
- `options_edge_scanner.data.loader.load_option_quotes(...)` now parses OCC-style `option_symbol` values and Trading Foundation `bid_price` / `ask_price` aliases so the raw snapshot schema can map into the repo's canonical option-quote contract
- scanner quote and spread filters now reject non-finite Trading Foundation inputs such as missing IV, spot, strike, or quote values before they reach probability/EV estimation
- the probability and EV layers now require finite positive spot, strike, IV, and time-to-expiration inputs so malformed contracts are rejected explicitly instead of surfacing later as `Estimated probability must be finite`
- manifest-derived Trading Foundation realized-underlying export now supports `--manifest` and `--realized-as-of`, so the workflow can export exact already-realized expiration dates instead of guessing a continuous range
- realized-outcome materialization now partitions required expirations into eligible versus future sets and excludes future expirations after the explicit cutoff instead of failing because their outcomes do not exist yet

Current limitation after the adapter build:

- the sandbox copy of `C:\GitHub\Trading_Foundation\historical_data\SPY` does not contain populated `option_snapshot/` or `eod/` folders, so real main-machine date coverage still needs an explicit audit
- the canonical main-machine root from the validation task, `C:\Users\RAS\OneDrive\RAS\Trading\Live\Trading_Foundation\historical_data`, is not mounted in this environment, so the exact May 27, 2025 through May 30, 2025 rerun could not be repeated here after the code fix
- the inspected sandbox Trading Foundation schema summary shows no guaranteed uniform snapshot-level timestamp column in `option_snapshot/`; when a raw file lacks one, the adapter emits day-precision `quote_observed_at` metadata derived from the file date rather than inventing intraday event-time precision
- SPY expiration-close outcome semantics remain the only explicit realized-outcome policy supported by this repo

## 1. Executive Summary

`options_edge_scanner` is a research-only offline options scanner centered on deterministic debit vertical spread screening from local option-chain snapshots. The maintained path is not a live-trading system. It is a contract-driven local analytics pipeline that:

- loads local option-chain CSV/parquet artifacts
- enforces point-in-time provenance rules
- generates same-expiration debit vertical spreads
- applies conservative execution and liquidity heuristics
- computes a versioned probability-of-profit contract and exact lognormal expected value for scanner-supported debit verticals
- ranks candidates and emits machine-readable CSV/JSON artifacts
- supports a separate calibration workflow with explicit prediction contracts, realized outcome contracts, and forward-only evaluation helpers

Current maturity:

- strong for offline contract validation, deterministic scanner orchestration, and calibration plumbing
- moderate for historical multi-snapshot research hygiene
- weak or nonexistent for live trading, true backtesting, portfolio construction, and production runtime concerns

What is actually working today:

- offline single-run scanning via `options_edge_scanner.cli.offline_scan`
- offline batch scanning via `options_edge_scanner.cli.offline_batch_scan`
- strict historical snapshot scanning via `options_edge_scanner.cli.historical_snapshot_scan`
- canonical Trading Foundation daily snapshot adaptation via `options_edge_scanner.cli.trading_foundation_snapshot_manifest`
- optional Yahoo artifact generation via `options_edge_scanner.cli.yahoo_option_chain_ingest`
- safe probability-prediction export via `options_edge_scanner.cli.export_probability_predictions`
- provider-neutral realized-underlying normalization plus Alpaca acquisition for outcome materialization
- canonical Trading Foundation EOD normalization for outcome materialization via `options_edge_scanner.cli.trading_foundation_realized_underlying_export`
- explicit realized-outcome materialization and calibration evaluation

What is partial, experimental, or intentionally not real yet:

- the probability model is still a simple `lognormal_breakeven` baseline, not an empirically calibrated alpha model
- the execution model is a conservative heuristic, not a historical fill simulator
- the backtest layer is a placeholder contract adapter only
- live/paper trading does not exist
- portfolio/risk controls are limited to filters and optional concentration caps
- only SPY expiration-close terminal outcome semantics are implemented for realized-outcome work

Deprecated or legacy surfaces:

- `run_scanner.py` is retired and intentionally only prints a migration message
- `options_edge_scanner.data.option_chain_loader.load_option_chain(...)` is a legacy live loader kept for narrow compatibility, not the maintained scanner path
- `options_edge_scanner.models.pricing`, `options_edge_scanner.signals.generator`, and `options_edge_scanner.utils.logger` are placeholders

Intended role in a broader trading/alpha-generation stack:

- this repo should serve as the reusable offline options-snapshot, spread-construction, point-in-time validation, candidate-ranking, and calibration-contract foundation
- it should not become the place where unrelated SEC/fundamental/filing ML stacks are copied wholesale
- future research modules should plug into its existing artifact and contract surfaces rather than rebuilding provenance checks, spread mechanics, or calibration join logic

## 2. Repository / System Architecture

### High-level architecture

Data ingestion:

- canonical maintained input is a local option-chain artifact loaded by `options_edge_scanner.data.loader.load_option_quotes(...)`
- optional upstream Yahoo ingestion lives in `options_edge_scanner.yahoo_ingestion` and `options_edge_scanner.cli.yahoo_option_chain_ingest`
- strict historical manifest loading lives in `options_edge_scanner.data.historical_snapshot_loader`
- canonical Trading Foundation manifest/metadata generation lives in `options_edge_scanner.data.trading_foundation`
- realized-underlying acquisition for calibration/outcome work lives in `options_edge_scanner.data.alpaca_historical`

Preprocessing / ETL:

- safe column alias normalization and type coercion in `options_edge_scanner.data.loader`
- provenance normalization, metadata-sidecar enrichment, and point-in-time validation in `options_edge_scanner.data.provenance`
- strict historical chain/metadata/spot co-validation in `options_edge_scanner.data.historical_snapshot_loader`
- realized-underlying normalization and validation in `options_edge_scanner.data.realized_underlying`
- realized-outcome materialization in `options_edge_scanner.calibration.materialization`

Universe construction:

- there is no repo-owned universe builder
- the effective universe is whatever ticker/expiration rows appear in the input artifact or strict manifest
- strict historical manifests define one logical snapshot per row, not a dynamic research universe engine

Feature generation:

- spread geometry and leg-level quote carry-through in `options_edge_scanner.scanner.spread_generator`
- `days_to_expiration`, spread market width, liquidity score, entry slippage, quoted vs execution-adjusted economics, predicted event threshold, and EV metrics are all generated inside the maintained scanner path
- there is no separate reusable feature store or feature registry yet

Screeners:

- quote-level and spread-level quality filters live in `options_edge_scanner.scanner.quality_filters`

Signal generation:

- there is no separate maintained signal-generation layer
- the ranked `ScannerOpportunityRow` output is the practical research signal surface today
- `options_edge_scanner.signals.generator.generate_edge_signals(...)` is a stub and should not be used

Ranking / scoring:

- ranking and optional concentration caps live in `options_edge_scanner.scanner.opportunity_ranker.rank_spreads(...)`

Backtesting / research:

- true backtesting is not implemented
- `options_edge_scanner.backtest.runner` is a placeholder contract adapter
- calibration evaluation and forward-only time windows are implemented in `options_edge_scanner.calibration`

Portfolio / risk management:

- only scan-level filters and optional per-ticker / per-expiration caps exist
- there is no account-, strategy-, or portfolio-level position sizing or exposure engine

Execution / order management:

- there is no order management or brokerage routing
- `options_edge_scanner.scanner.execution` adjusts entry economics heuristically for research ranking only

Reporting / artifacts:

- ranked scanner output is CSV
- optional scan report is JSON via `options_edge_scanner.scanner.reporting`
- calibration outputs are CSV summaries / bins / joined observations
- realized-underlying and realized-outcome artifacts are CSV plus JSON sidecars where relevant

Notebooks:

- `notebooks/01_offline_scanner_demo.ipynb` is a workflow demo only
- it does not introduce extra signal logic beyond calling the maintained CLI and plotting outputs

CLI / scripts:

- maintained CLIs:
  - `options_edge_scanner.cli.offline_scan`
  - `options_edge_scanner.cli.offline_batch_scan`
  - `options_edge_scanner.cli.historical_snapshot_scan`
  - `options_edge_scanner.cli.export_probability_predictions`
  - `options_edge_scanner.cli.probability_calibration_eval`
  - `options_edge_scanner.cli.alpaca_realized_underlying_acquire`
  - `options_edge_scanner.cli.materialize_realized_outcomes`
  - `options_edge_scanner.cli.yahoo_option_chain_ingest`
- retired entrypoint:
  - `run_scanner.py`

APIs / external services:

- `yfinance` is used only for optional Yahoo option-chain ingestion
- Alpaca market data is used only for realized-underlying acquisition in calibration/outcome workflows
- there is no live broker API integration for orders

### End-to-end data flow

Maintained scanner flow:

```text
local option-chain CSV/parquet
-> load_option_quotes()
-> enrich_option_quote_provenance()
-> resolve_effective_as_of() + validate_point_in_time_integrity()
-> apply_option_quote_quality_filters()
-> generate_vertical_spreads()
-> apply_execution_adjustments()
-> apply_spread_quality_filters()
-> predict_spread_probability()
-> calculate_expected_value()
-> rank_spreads()
-> ScannerOpportunityRow CSV
-> optional scan report JSON
```

Strict historical + calibration flow:

```text
strict historical snapshot manifest
-> load_historical_snapshots()
-> build_scanner_opportunities() per snapshot
-> combined historical ScannerOpportunityRow CSV
-> export_scanner_probability_predictions()
-> ProbabilityPredictionRow CSV

normalized realized-underlying CSV(s)
-> materialize_realized_outcomes_from_snapshot_manifest()
-> RealizedOutcomeRow CSV

ProbabilityPredictionRow + RealizedOutcomeRow
-> evaluate_probability_predictions()
-> calibration summary / reliability bins / joined observations
```

## 3. Data Contracts

The authoritative contract narratives are `docs/data_contracts.md`, `docs/calibration_contracts.md`, and `docs/backtest_contracts.md`. The important practical contracts are:

### OptionQuoteRow

Purpose:

- canonical normalized option-quote input for the maintained scanner

Primary producer:

- `options_edge_scanner.data.loader.load_option_quotes(...)`
- optionally `options_edge_scanner.yahoo_ingestion.ingest_yahoo_option_chain(...)`

Primary consumers:

- `options_edge_scanner.scanner.engine.build_scanner_artifacts(...)`
- `options_edge_scanner.data.historical_snapshot_loader.load_historical_snapshot(...)`

Required fields:

- `ticker`
- `expiration`
- `strike`
- `type`
- `bid`
- `ask`
- `implied_vol`
- `underlying_price` unless supplied safely via `--spot`

Important optional provenance fields:

- `snapshot_id`
- `snapshot_source`
- `quote_observed_at`
- `underlying_price_observed_at`
- `underlying_price_source`
- `input_path`
- `source_metadata_path`

Normalization rules:

- safe aliases include `option_type`, `expiry`, `expiry_date`, `expiration_date`, `strike_price`, `iv`, and `implied_volatility`
- `mid` is derived from `(bid + ask) / 2` when missing
- `type` is normalized to `call` / `put`
- timestamps are normalized through `options_edge_scanner.data.provenance`

Point-in-time assumptions:

- safe scans require non-empty `quote_observed_at`
- if `underlying_price_observed_at` is present, it is also validated against `as_of`
- date-only `as_of` values use day-level comparisons; timestamp-valued `as_of` values use full timestamp precision

Persistence:

- arbitrary local CSV/parquet file path
- examples exist under `outputs/` and `tests/fixtures/`

Canonical downstream use:

- this is the canonical raw-input contract for all options-snapshot research inside this repo

### Metadata sidecar (`<input>.meta.json`)

Purpose:

- optional provenance enrichment sidecar for local input artifacts

Used by:

- `options_edge_scanner.data.provenance.enrich_option_quote_provenance(...)`
- `options_edge_scanner.data.historical_snapshot_loader`

Important fields when used in the maintained safe path:

- `snapshot_id`
- `snapshot_source`
- `quote_observed_at`
- `underlying_price`
- `underlying_price_observed_at`
- `underlying_price_source`

Important caveat:

- current repo-local Yahoo sidecars under `outputs/yahoo_option_chains/*.meta.json` are legacy examples and are not safe current inputs because they are missing `snapshot_id`

### HistoricalSnapshotManifestRow

Purpose:

- strict manifest row describing one logical historical snapshot

Producer:

- user-authored manifest CSV/JSON

Consumer:

- `options_edge_scanner.data.historical_snapshot_loader.load_historical_snapshots(...)`
- `options_edge_scanner.cli.historical_snapshot_scan`
- `options_edge_scanner.calibration.materialization.collect_required_outcome_requests_from_manifest(...)`

Required fields:

- `snapshot_id`
- `ticker`
- `as_of`
- `chain_path`
- `metadata_path`

Important rules:

- `snapshot_id` must be unique
- `chain_path` and `metadata_path` resolve relative to the manifest file
- duplicate resolved chain or metadata artifacts are rejected
- authoritative provenance can come from manifest row and/or metadata sidecar, but disagreements are rejected
- `quote_observed_at` and `underlying_price_observed_at` must match exactly for strict historical use
- no unsafe historical bypass exists

Canonical downstream use:

- this is the canonical input surface for historical options research and calibration-ready scanning

### VerticalSpreadRow

Purpose:

- internal canonical spread row emitted by `generate_vertical_spreads(...)`

Producer:

- `options_edge_scanner.scanner.spread_generator.generate_vertical_spreads(...)`

Consumers:

- `apply_execution_adjustments(...)`
- `apply_spread_quality_filters(...)`
- probability and EV calculations

Implemented spread families:

- `bull_call_debit`
- `bear_put_debit`

Important rules:

- same ticker, same expiration, same provenance group
- same `underlying_price`
- width must be positive and at most 10 points
- only `0 < debit < width` spreads survive

Canonical downstream use:

- internal reusable spread contract; future options modules should reuse this instead of rebuilding leg-pairing logic

### ScannerOpportunityRow

Purpose:

- ranked scanner output row and current practical research-signal surface

Producer:

- `options_edge_scanner.scanner.engine.build_scanner_artifacts(...)`
- CLI wrappers around that engine

Consumers:

- researchers
- `export_scanner_probability_predictions(...)`
- future research notebooks

Critical fields:

- spread structure: `spread_type`, `lower_strike`, `upper_strike`, `long_strike`, `short_strike`, `width`
- provenance: `snapshot_id`, `snapshot_source`, `quote_observed_at`, `underlying_price_observed_at`, `underlying_price_source`, `input_path`, `source_metadata_path`
- timing: `as_of`, `expiration`, `days_to_expiration`
- execution diagnostics: `quoted_debit`, `debit`, `spread_bid`, `spread_ask`, `spread_market_width`, `entry_slippage`, `entry_price_policy`, `liquidity_score`
- model semantics: `probability_model_name`, `probability_model_version`, `predicted_event_name`, `predicted_event_direction`, `predicted_event_operator`, `predicted_event_threshold`, `predicted_event_horizon`
- economics: `probability_of_profit`, `expected_value`, `theoretical_expected_value`, `edge_pct`, `avg_profit`, `avg_loss`, `ranking_score`, `selection_rank`

Point-in-time assumptions:

- safe outputs only exist if the upstream scan passed provenance validation

Canonical downstream use:

- canonical ranked-candidate artifact for options spread research
- canonical input to calibration export only when `snapshot_id` and model-event fields are present

### Scan report JSON

Purpose:

- machine-readable audit artifact for single-run offline scans

Producer:

- `options_edge_scanner.scanner.reporting.build_scan_report(...)`
- `options_edge_scanner.cli.offline_scan --report-output`

Critical fields:

- counts from each major pipeline stage
- execution assumptions
- selection assumptions
- model/version inventory
- result summary
- top opportunities

Canonical downstream use:

- human and machine audit of scan behavior
- not a research result dataset by itself

### ProbabilityPredictionRow

Purpose:

- canonical prediction-side artifact for calibration/evaluation

Producer:

- `options_edge_scanner.calibration.evaluation.export_scanner_probability_predictions(...)`
- `options_edge_scanner.cli.export_probability_predictions`

Consumers:

- `evaluate_probability_predictions(...)`
- calibration notebooks / downstream scoring studies

Critical fields:

- identity: `prediction_id`, `snapshot_id`, `observation_group_id`
- timing: `prediction_timestamp`, `quote_observed_at`, `as_of`, `expiration`
- spread structure: `spread_type`, `lower_strike`, `upper_strike`, `long_strike`, `short_strike`
- model semantics: `predicted_probability`, `probability_model_name`, `probability_model_version`, `predicted_event_name`, `predicted_event_direction`, `predicted_event_operator`, `predicted_event_threshold`, `predicted_event_horizon`
- linkage: `required_outcome_horizon`, `required_outcome_key`

Point-in-time assumptions:

- prediction timestamps must be full ISO-8601 with timezone
- predictions must be observed before the expiration date for `expiration` horizon
- duplicate semantic predictions are rejected

Canonical downstream use:

- this is the canonical calibration-ready prediction artifact

### RealizedUnderlyingObservationRow

Purpose:

- provider-neutral local artifact representing the realized underlying observation used to resolve future outcomes

Primary producers:

- `options_edge_scanner.data.alpaca_historical.normalize_alpaca_stock_bars_to_realized_underlying(...)`
- `options_edge_scanner.cli.alpaca_realized_underlying_acquire`

Primary consumers:

- `options_edge_scanner.calibration.materialization.materialize_realized_outcomes(...)`

Critical fields:

- `observation_id`
- `required_outcome_key`
- `ticker`
- `event_date`
- `required_outcome_horizon`
- `realized_outcome_measure`
- `terminal_price_convention`
- `terminal_price_convention_version`
- `observed_price`
- `observed_at`
- `market_close_timestamp`
- `price_field`
- `observed_market_session`
- `source`
- `source_dataset`
- `source_feed`
- `timeframe`
- `adjustment_mode`
- `acquired_at`
- `provenance_artifact_id`

Current scope:

- only SPY expiration-close policy is explicitly supported

Canonical downstream use:

- canonical pre-outcome artifact for outcome materialization

### RealizedOutcomeRow

Purpose:

- separate future-outcome artifact joined against predictions for calibration/evaluation

Primary producers:

- `options_edge_scanner.calibration.materialization.materialize_realized_outcomes(...)`
- `options_edge_scanner.cli.materialize_realized_outcomes`

Primary consumers:

- `evaluate_probability_predictions(...)`

Critical fields:

- `outcome_id`
- `required_outcome_key`
- `ticker`
- `expiration`
- `required_outcome_horizon`
- `realized_outcome_measure`
- `realized_terminal_underlying_price`
- `realized_outcome_observed_at`
- `realized_outcome_source`

Canonical downstream use:

- canonical realized-outcome artifact for calibration/evaluation

### Calibration evaluation artifacts

Purpose:

- machine-readable scoring outputs for prediction vs realized-outcome comparisons

Producer:

- `options_edge_scanner.calibration.evaluation.evaluate_probability_predictions(...)`
- `options_edge_scanner.cli.probability_calibration_eval`

Artifacts:

- joined observations CSV
- reliability bins CSV
- one-row calibration summary CSV

Canonical downstream use:

- evaluation and diagnostics, not trading decisions

### Backtest contracts

Purpose:

- placeholder scaffolding for future backtest integration

Files:

- `docs/backtest_contracts.md`
- `options_edge_scanner.backtest.runner`
- `tests/fixtures/sample_backtest_*.csv`

Important truth:

- these are contract placeholders, not empirical backtest outputs

## 4. Signals, Screens, and Trading Logic

The maintained repo does not yet have a general signal engine. The implemented logic is concentrated in filters, spread generation, ranking, and calibration semantics.

| Logic | Location | Purpose | Implemented logic / defaults | Inputs | Outputs | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Safe alias normalization | `options_edge_scanner.data.loader` | Accept predictable local schema variants | Renames `option_type`, `expiry`, `expiry_date`, `expiration_date`, `strike_price`, `iv`, `implied_volatility` to canonical names | raw local option-chain frame | normalized `OptionQuoteRow` frame | implemented and tested |
| Mid derivation | `options_edge_scanner.data.loader.validate_option_quote_frame(...)` | Avoid requiring a precomputed midpoint | `mid = (bid + ask) / 2` when missing | `bid`, `ask` | populated `mid` | implemented and tested |
| Provenance enrichment | `options_edge_scanner.data.provenance.enrich_option_quote_provenance(...)` | Carry snapshot identity and timestamps into safe scans | reads sibling `.meta.json`; fills `snapshot_id`, `snapshot_source`, `quote_observed_at`, `underlying_price_observed_at`, `underlying_price_source` | local quote file plus optional metadata sidecar | enriched quote rows | implemented and tested |
| Point-in-time validation | `options_edge_scanner.data.provenance.validate_point_in_time_integrity(...)` | Block lookahead and missing-provenance scans by default | rejects missing `quote_observed_at`, rejects `as_of` before observed timestamps, allows explicit unsafe override only in ad hoc path | enriched quotes, `as_of` | validated quotes or failure | implemented and tested |
| Quote moneyness screen | `apply_option_quote_quality_filters(...)` | Remove legs too far from spot | keeps `abs(strike - spot) / spot <= 0.25` by default | quote rows | filtered quotes | implemented and tested |
| Quote bid/ask quality screen | `apply_option_quote_quality_filters(...)` | Remove wide or structurally bad legs | requires valid non-negative quotes and `(ask - bid) / mid <= 0.25` by default | quote rows | filtered quotes | implemented and tested |
| Optional quote volume / OI / delta filters | `apply_option_quote_quality_filters(...)` | Allow stricter quality screens when data exists | optional `min_volume`, `min_open_interest`, `min_abs_delta`, `max_abs_delta` | quote rows | filtered quotes | implemented and tested at contract level |
| Vertical spread generation | `generate_vertical_spreads(...)` | Build canonical scanner-supported spreads | generates `bull_call_debit` and `bear_put_debit` from same ticker/expiration/provenance pairs with `0 < width <= 10` and `0 < debit < width` | filtered quote rows | `VerticalSpreadRow` frame | implemented and tested |
| Spread liquidity features | `apply_execution_adjustments(...)` | Estimate how executable a spread is | derives `spread_bid`, `spread_ask`, `spread_market_width`, `spread_min_volume`, `spread_min_open_interest`, `leg_relative_spread_mean`, `liquidity_score` | spread rows with leg quotes | enriched spread rows | implemented and tested through pipeline coverage |
| Entry slippage model | `apply_execution_adjustments(...)` | Penalize midpoint entry conservatively | fill fraction interpolates between `execution_slippage_floor=0.2` and `execution_slippage_cap=0.5` based on liquidity; execution debit is midpoint plus penalty capped at spread ask | spread rows plus quality settings | execution-adjusted spread economics | implemented and tested through pipeline coverage |
| Spread debit-fraction screen | `apply_spread_quality_filters(...)` | Reject poor payoff ratios | default `debit / width <= 0.67` | enriched spread rows | filtered spreads | implemented and tested |
| Spread market-width screen | `apply_spread_quality_filters(...)` | Reject very wide spread markets | default `spread_market_width / quoted_debit <= 0.8` | enriched spread rows | filtered spreads | implemented and tested |
| Probability model | `options_edge_scanner.models.probability_models` and `options_edge_scanner.models.probability_estimator` | Estimate spread breakeven-tail probability | current maintained model is `lognormal_breakeven` version `1`; debit verticals map to `terminal_underlying_crosses_spread_breakeven` at expiration | `underlying_price`, strikes, implied vol, DTE, spread type, debit | `ProbabilityModelPrediction` | implemented and unit tested |
| Exact EV model | `options_edge_scanner.models.spread_ev_calculator.calculate_expected_value(...)` | Compute scanner EV | exact lognormal expected payoff for maintained debit verticals; subtracts fixed `TRANSACTION_COST = 0.05`; emits `expected_value`, `edge_pct`, `avg_profit`, `avg_loss`, `prob_win`, `prob_loss`, `ev_method=lognormal_vertical_exact` | spread row with spot, IV, DTE | EV metrics | implemented and unit tested |
| Ranking filter | `rank_spreads(...)` | Decide what survives to ranked output | requires `expected_value > min_expected_value` and `probability > min_probability_of_profit`, defaults `0.0` and `0.3` | scanner opportunity rows | eligible candidates | implemented and tested |
| Ranking score | `rank_spreads(...)` | Prefer higher-EV, higher-liquidity candidates | `ranking_score = expected_value * (0.5 + 0.5 * liquidity_score)` | eligible candidates | sorted candidates | implemented and tested |
| Concentration caps | `rank_spreads(...)` | Reduce ticker/expiration concentration | optional `max_positions_per_ticker` and `max_positions_per_expiration` | ranked candidates | final selected rows | implemented and tested at contract level |
| Calibration export semantics | `export_scanner_probability_predictions(...)` | Preserve exact model-event meaning downstream | builds `prediction_id`, `required_outcome_key`, and `observation_group_id`; requires non-empty `snapshot_id` | safe `ScannerOpportunityRow` frame | `ProbabilityPredictionRow` frame | implemented and tested |
| Forward-only calibration windows | `options_edge_scanner.calibration.time_windows` | Prevent random-split leakage | fixed holdout, expanding, and rolling windows over prediction timestamps | prediction frame | window specs | implemented and unit tested |
| Entry condition in maintained system | implicit in scanner path | Define what counts as a candidate | a row is effectively "enterable" only if it survives all filters and remains inside the top-N ranked output | scanner opportunity rows | ranked research candidates | implemented |
| Exit condition in maintained system | not implemented; placeholder only in `backtest/runner.py` | Future lifecycle modeling hook | placeholder exit is expiration with `exit_reason=expiration_placeholder` and `realized_pnl=0.0` | backtest signal frame | placeholder trade result rows | placeholder only |
| Portfolio rule in maintained system | `rank_spreads(...)` only | Keep output list bounded | `top_n` plus optional ticker/expiration caps | ranked candidates | final selected rows | implemented but minimal |

Important unused-but-present logic:

- `estimate_probability_of_profit(...)` and `calculate_expected_value(...)` contain code paths for credit-spread semantics, but the maintained scanner never generates credit spreads today
- the notebook contains no additional trading logic beyond calling `offline_scan` and plotting the result

## 5. Risk Controls

### Actually enforced today

| Control | Location | Enforced behavior | Notes |
| --- | --- | --- | --- |
| Missing quote-provenance rejection | `validate_point_in_time_integrity(...)` | fails scans lacking `quote_observed_at` unless `--allow-unsafe-as-of` is set | primary offline safety gate |
| Lookahead rejection | `validate_point_in_time_integrity(...)` | rejects `as_of` earlier than quote or spot observation timestamp | supports day-level and full-timestamp modes |
| Spot-override provenance requirement | `offline_scan.py`, `scanner.engine.run_scan(...)` | safe `--spot` usage requires `--spot-observed-at`; otherwise caller must opt into unsafe mode | prevents stale inherited spot provenance |
| Strict same-snapshot historical policy | `historical_snapshot_loader.load_historical_snapshot(...)` | rejects historical snapshots where option quotes and spot reference do not share the exact same observation timestamp | there is no unsafe historical bypass |
| Snapshot identity enforcement | `historical_snapshot_loader`, `calibration.evaluation` | requires `snapshot_id` for strict historical and calibration-ready workflows | blocks ambiguous artifact joins |
| Quote quality filters | `quality_filters.apply_option_quote_quality_filters(...)` | filters moneyness, bid/ask spread, optional volume/OI/delta | risk reduction is heuristic, not economic |
| Spread quality filters | `quality_filters.apply_spread_quality_filters(...)` | filters spread economics and optional liquidity thresholds | screening control only |
| Execution penalty | `scanner.execution.apply_execution_adjustments(...)` | makes entry economics more conservative than midpoint | not a true cost model |
| Concentration caps | `rank_spreads(...)` | optional per-ticker and per-expiration limits | the only portfolio-like control present |
| Shared-outcome-key rejection | `join_predictions_with_realized_outcomes(...)` | rejects correlated repeated predictions against one outcome by default | calibration leakage control |
| Forward-only evaluation helpers | `calibration.time_windows` | fixed holdout / expanding / rolling only | no random split default |
| Realized-outcome timing checks | `validate_realized_outcome_frame(...)`, `join_predictions_with_realized_outcomes(...)` | realized outcomes must be on/after expiration and strictly later than prediction and quote timestamps | calibration leakage control |
| Explicit terminal observation policy | `terminal_semantics.py`, `realized_underlying.py` | rejects unsupported ticker/horizon combinations and non-trading-day event dates | currently SPY-only |

### Not implemented today

- kill switches
- account-level loss limits
- drawdown throttles
- position sizing
- leverage or margin limits
- strategy-level gross/net exposure controls
- broker/account reconciliation
- live alerting / paging / circuit breakers
- portfolio Greeks or factor exposure controls

### Fail-safe behavior

- the maintained path fails closed through explicit exceptions rather than silently proceeding
- strict historical scan captures row-level failures in its summary output instead of silently dropping bad snapshots
- outcome materialization refuses to forward-fill, roll dates, or reuse cross-symbol data

## 6. Backtesting and Validation

### What exists

Scanner validation:

- broad fixture-driven regression coverage across loader, CLI, historical manifests, probability model, EV model, calibration contracts, realized-underlying contracts, and placeholder backtest contracts
- deterministic pipeline validation in `tests/test_scanner_pipeline_integration.py`

Calibration validation:

- contract validators for `ProbabilityPredictionRow` and `RealizedOutcomeRow`
- deterministic evaluation metrics: Brier score, log loss, ECE, MCE
- forward-only window helpers in `options_edge_scanner.calibration.time_windows`

Backtest surface:

- `options_edge_scanner.backtest.runner` produces placeholder-shaped trade results and summary rows only
- it validates signal and exit-fixture schemas
- it does not model true fills, PnL, or exits

### What does not exist

- no real options lifecycle backtester
- no transaction-level fill simulation
- no assignment / early-exercise modeling
- no benchmark comparison framework
- no walk-forward strategy-validation pipeline attached to an empirical dataset
- no portfolio replay

### Assumptions in the maintained scanner

- terminal underlying follows a lognormal distribution under the repo's current baseline assumption
- implied volatility is constant to expiration inside the current model
- DTE uses `252` trading days per year in the maintained probability / exact EV stack
- exact EV subtracts a fixed `0.05` transaction-cost penalty
- execution realism is approximated heuristically from quoted widths and optional size data

### Important validated results

- `pytest -q` passed with `152` tests on 2026-08-17
- `python -m compileall options_edge_scanner run_scanner.py` passed on 2026-08-17
- practical validation showed that `outputs/historical_snapshots/spy_candidates.csv` is compatible with current calibration export and yielded 40 predictions
- practical validation also showed that several repo-local sample artifacts are stale under the current stricter contracts:
  - `outputs/offline_scan_sample.csv` is not calibration-ready
  - `outputs/yahoo_option_chains/SPY_2026-06-15_yahoo.csv.meta.json` lacks the now-required `snapshot_id`

### Existing experiments and evidence

- the notebook `notebooks/01_offline_scanner_demo.ipynb` demonstrates the offline scan workflow
- repo-local historical scan artifacts under `outputs/historical_snapshots/` show that strict multi-snapshot scanning works mechanically
- calibration tests include synthetic and fixture-based evaluation checks

### Methodological weaknesses

- no empirical evidence that the current probability model is alpha-bearing
- no serious realized prediction/outcome dataset is present yet
- no benchmark or baseline-comparison literature is embedded in repo outputs
- no historical execution simulator exists
- current realized-outcome semantics are limited to SPY expiration-close proxy logic
- current scanner only supports debit verticals and a hard width cap of 10 points

## 7. Live / Paper Trading Integration

There is no live or paper trading stack in this repository.

What exists:

- Alpaca integration only for historical stock-bar acquisition used in realized-underlying normalization
- optional Yahoo ingestion only for local option-chain artifact generation

What does not exist:

- brokerage order placement
- order lifecycle management
- paper-trading behavior
- scheduling daemon
- alerting
- OMS / EMS
- live market-data runtime for the maintained scanner path
- production logging stack

Readiness level:

- not ready for live or paper trading
- intentionally out of scope per README and current code

## 8. Existing Artifacts and Proven Outputs

| Artifact | Role | Trust level | Notes |
| --- | --- | --- | --- |
| `docs/offline_gap_audit_2026-08-17.md` | latest closeout/gate note | high | aligned with current code and tests |
| `docs/offline_scanner_readiness_review.md` | current repo-status summary | high | useful companion to this handoff |
| `docs/data_contracts.md` | scanner and data contract narrative | high | tracks current maintained contracts closely |
| `docs/calibration_contracts.md` | calibration contract narrative | high | tracks current maintained calibration path closely |
| `docs/backtest_contracts.md` | placeholder backtest contract narrative | high | authoritative for what the placeholder layer is and is not |
| `outputs/historical_snapshots/spy_candidates.csv` | combined strict historical candidate example | medium-high | schema-valid enough to export to calibration predictions under current code; not strategy proof |
| `outputs/historical_snapshots/spy_summary.csv` | per-snapshot historical scan summary | medium-high | good example of row-level historical success accounting |
| `outputs/closeout_audit/offline_scan_report.json` | scan report schema example | medium | useful for JSON contract shape and counts |
| `outputs/closeout_audit/calibration_summary.csv`, `calibration_bins.csv`, `calibration_observations.csv` | calibration output examples | medium | useful for schema examples, not empirical claims |
| `notebooks/01_offline_scanner_demo.ipynb` | walkthrough/demo | medium | explains current offline flow, no extra alpha logic |
| `outputs/offline_scan_sample.csv` and `outputs/offline_batch_scan_sample.csv` | local sample outputs | low | useful as examples only; not current calibration-ready artifacts |
| `outputs/closeout_audit/offline_scan_predictions.csv` | legacy prediction export example | low | stale under current snapshot-id contract; do not treat as authoritative |
| `outputs/yahoo_option_chains/*.csv` and `*.meta.json` | repo-local Yahoo artifacts | low | useful for inventory and schema examples only; current sidecars are not safe current inputs |

### Canonical artifacts future work should consume

Treat these as canonical first:

- `OptionQuoteRow` local input artifacts that satisfy current safe provenance rules
- strict historical snapshot manifests plus matching metadata sidecars
- `ScannerOpportunityRow` outputs from the maintained scanner when they include `snapshot_id` and full model-event semantics
- `ProbabilityPredictionRow` outputs from `export_scanner_probability_predictions(...)`
- `RealizedUnderlyingObservationRow` and `RealizedOutcomeRow` artifacts for outcome evaluation

Treat these as non-canonical or legacy:

- repo-local Yahoo sample sidecars missing `snapshot_id`
- old demo/sample scan outputs missing current export metadata
- any artifact generated via unsafe ad hoc scanning without current provenance fields

## 9. Reusable Components

### DO NOT REBUILD

| Reuse this | Exact file / function | Why it should be reused |
| --- | --- | --- |
| Local option-chain loader | `options_edge_scanner.data.loader.load_option_quotes(...)` and `validate_option_quote_frame(...)` | already handles canonical schema, aliases, type coercion, and midpoint derivation |
| Provenance handling | `options_edge_scanner.data.provenance.enrich_option_quote_provenance(...)`, `resolve_effective_as_of(...)`, `validate_point_in_time_integrity(...)` | this is the current point-in-time safety layer; rebuilding it elsewhere invites leakage |
| Strict historical manifest loader | `options_edge_scanner.data.historical_snapshot_loader.load_historical_snapshots(...)` | already solves manifest-relative paths, duplicate detection, same-snapshot enforcement, and explicit snapshot IDs |
| Spread constructor | `options_edge_scanner.scanner.spread_generator.generate_vertical_spreads(...)` | canonical same-expiration debit vertical construction logic lives here |
| Execution-aware economics | `options_edge_scanner.scanner.execution.apply_execution_adjustments(...)` | current heuristic entry-pricing and liquidity diagnostics are already encoded here |
| Quote / spread filters | `options_edge_scanner.scanner.quality_filters.OfflineScanQualitySettings`, `apply_option_quote_quality_filters(...)`, `apply_spread_quality_filters(...)` | central place for maintained conservative filters and parameterization |
| Probability model wrapper | `options_edge_scanner.models.probability_models.predict_spread_probability(...)` and `LognormalBreakevenProbabilityModel` | preserves versioned model semantics and exact predicted-event metadata |
| EV calculator | `options_edge_scanner.models.spread_ev_calculator.calculate_expected_value(...)` | canonical exact EV logic for the maintained debit scanner path |
| Scanner orchestration | `options_edge_scanner.scanner.engine.build_scanner_artifacts(...)`, `build_scanner_opportunities(...)`, `run_scan(...)` | central maintained pipeline entry point |
| Ranking logic | `options_edge_scanner.scanner.opportunity_ranker.rank_spreads(...)` | contains current selection thresholds, score, and concentration-cap behavior |
| Scan reporting | `options_edge_scanner.scanner.reporting.build_scan_report(...)` and `write_scan_report(...)` | current JSON report contract lives here |
| Prediction export | `options_edge_scanner.calibration.evaluation.export_scanner_probability_predictions(...)` | builds stable calibration-ready prediction artifacts |
| Calibration validation | `options_edge_scanner.calibration.contracts.validate_probability_prediction_frame(...)` and `validate_realized_outcome_frame(...)` | canonical schema and leakage validation lives here |
| Calibration scoring | `options_edge_scanner.calibration.evaluation.evaluate_probability_predictions(...)` | already computes joined observations, reliability bins, and summary metrics |
| Outcome join keys | `build_required_outcome_key(...)`, `build_observation_group_id(...)`, `build_prediction_id(...)` | these IDs are the repo's current clean integration contract |
| Terminal outcome semantics | `options_edge_scanner.calibration.terminal_semantics` | explicit SPY expiration-close policy is already encoded here |
| Realized-underlying normalization | `options_edge_scanner.data.realized_underlying` and `options_edge_scanner.data.alpaca_historical` | do not recreate provider-normalization and policy validation logic elsewhere |
| Outcome materialization | `options_edge_scanner.calibration.materialization.materialize_realized_outcomes(...)` | current realized-outcome contract builder |
| Maintained CLIs | all modules under `options_edge_scanner.cli` except `run_scanner.py` | future automation should call the existing maintained CLIs rather than scripting one-off loaders |
| Contract fixtures | `tests/fixtures/` and related tests | the repo already has stable regression fixtures for key contract surfaces |

### Reuse with caution

- `outputs/historical_snapshots/spy_candidates.csv` is useful as a shape example and exportable under current code, but it is not empirical alpha proof
- `options_edge_scanner.data.option_chain_loader.load_option_chain(...)` is legacy compatibility code, not a preferred new dependency

### Do not treat as reusable building blocks

- `options_edge_scanner.models.pricing.estimate_fair_value(...)`
- `options_edge_scanner.signals.generator.generate_edge_signals(...)`
- `options_edge_scanner.utils.logger.get_logger(...)`
- `options_edge_scanner.backtest.runner` as a true backtester

Those surfaces are placeholders and should be implemented properly or bypassed until a real design lands.

## 10. Known Gaps / Technical Debt

### Genuine blockers

1. There is no maintained strict option-chain acquisition source with trusted point-in-time quote timestamps baked into repo-local artifacts.
2. Current repo-local Yahoo sidecars are stale under the current safe contract because they lack `snapshot_id`.
3. There is no meaningful empirical prediction/outcome dataset large enough to support serious calibration or alpha claims.
4. There is no real options lifecycle backtester or execution simulator.
5. There is no generalized research-signal contract beyond the current options-scanner / calibration surfaces.

### Worthwhile improvements

1. Add end-to-end model selection/configuration instead of hardwiring `lognormal_breakeven`.
2. Extend supported strategy families beyond debit verticals, or explicitly keep the repo narrow and document that as a hard scope line.
3. Replace or augment the heuristic execution model with richer historical microstructure assumptions once data exists.
4. Add a real logging layer and structured runtime diagnostics.
5. Clean or archive stale example artifacts under `outputs/` so repo-local examples align with current contracts.
6. Introduce a formal promotion path from notebook research into package modules and CLIs.

### Optional enhancements

1. Add richer report generation and artifact packaging around scan/calibration runs.
2. Add broader vendor adapters for option-chain ingestion if trusted point-in-time data becomes available.
3. Add more fixture breadth for additional symbols, expirations, and vendor-specific edge cases.
4. Add a generalized research metadata schema for notebooks and experiment runs.

### Stale or contradictory documentation to treat carefully

1. `docs/pipeline_review.md` is a historical March 2026 review of a much earlier state. It accurately describes old weaknesses, but it no longer describes the maintained offline scanner as of August 17, 2026.
2. `docs/system_quant_correctness_review_2026-03-28.md` is likewise a pre-hardening critique. It remains useful as historical context, but several issues it raises are now partially or fully addressed in the current maintained path.
3. `docs/options_edge_scanner_next_workstream_review.md` is explicitly marked historical, and its discussion of batch manifest path behavior no longer matches current code or tests. Current behavior is manifest-relative path resolution for batch inputs and outputs.
4. Several repo-local example artifacts under `outputs/` predate stricter `snapshot_id` and calibration-export requirements, so artifact age matters as much as code age in this repository.

### Deliberately out-of-scope items in the current repo

1. Live broker integration and order routing.
2. Autonomous execution.
3. Production portfolio-management stack.
4. Folding SEC/fundamental/filing ML research directly into this codebase.

## 11. Integration Contract for Future Alpha Research

Recommended flow for future work:

```text
universe
-> market data / option snapshot artifacts
-> canonical features / provenance validation
-> signal logic
-> ranked candidates
-> backtest or calibration evidence
-> validated strategy module
-> future risk / execution layer
```

For options-snapshot work inside this repo, the preferred concrete flow is:

```text
strict snapshot manifest or safe local chain
-> OptionQuoteRow
-> maintained scanner utilities
-> ScannerOpportunityRow
-> ProbabilityPredictionRow when evaluating event probabilities
-> RealizedOutcomeRow
-> calibration / future backtest evidence
```

### What future modules should consume

Options-oriented research should consume one of:

- `OptionQuoteRow` plus current provenance fields
- `VerticalSpreadRow` if the module operates after spread generation
- `ScannerOpportunityRow` if the module is ranking, calibration, or post-scan analysis
- `ProbabilityPredictionRow` and `RealizedOutcomeRow` for calibration/evaluation work

Non-options price/returns research can borrow this repo's discipline without forcing itself into spread contracts:

- reuse point-in-time provenance ideas, artifact IDs, outcome keys, and forward-only evaluation patterns
- do not force unrelated return models to pretend they are vertical spreads

### What future modules should output

If the module is an options-spread research extension:

- output a superset of `ScannerOpportunityRow` or `ProbabilityPredictionRow`
- preserve `snapshot_id`, `as_of`, `quote_observed_at`, and exact predicted-event semantics
- keep one row per logical opportunity / prediction

If the module is a broader price/returns-based alpha notebook:

- recommended minimum output contract:
  - `module_name`
  - `module_version`
  - `snapshot_id` or equivalent observation ID
  - `ticker`
  - `as_of`
  - `signal_name`
  - `signal_score` or `predicted_probability`
  - `horizon`
  - `required_outcome_key` when outcome evaluation is intended
  - references to input artifacts

The previous bullet is a recommendation, not an already-implemented repo contract.

### Minimum schemas / contracts to respect

1. Never bypass `snapshot_id` when producing calibration-ready predictions.
2. Never drop `quote_observed_at` or `as_of` if a module will make forward claims.
3. Preserve explicit event semantics rather than storing only a probability scalar.
4. Use manifest-relative artifact references when moving datasets between machines.
5. Keep predictions and realized outcomes in separate artifacts.

### How signals should be represented

Current best practice inside this repo:

- use `ScannerOpportunityRow` when the object is still a ranked options candidate
- use `ProbabilityPredictionRow` when the object is a forecast to be evaluated later

Avoid:

- opaque notebook-only CSVs with no `snapshot_id`
- outputs that collapse event semantics into unlabeled score columns
- direct dependence on legacy sample artifacts that fail current validators

### How research results should be promoted into the existing system

1. Prototype in a notebook or isolated module using current loader/provenance/scanner utilities.
2. If the result is still options-snapshot based, keep the interface aligned with current contracts instead of inventing a parallel schema.
3. Add a package module under `options_edge_scanner/` only after the idea has deterministic local artifacts and a clear contract.
4. Add tests first around schema, PIT safety, and deterministic outputs.
5. Add or update a CLI only after the module has a stable contract.
6. Update `docs/data_contracts.md`, `docs/calibration_contracts.md`, or this handoff when the interface changes.

### Practical implications for specific future work

Mean reversion:

- should reuse PIT discipline, scan/report artifact patterns, and future evaluation contracts
- likely needs its own non-spread signal schema unless it is explicitly trading option spreads

PEAD / event-driven alpha:

- should stay separate from SEC/fundamental ML ingestion unless this repo genuinely depends on that system
- can still reuse `required_outcome_key` style outcome linking and forward-only evaluation ideas

Volatility / VIX / term-structure research:

- can likely reuse local artifact discipline and ranking/reporting patterns
- should avoid rebuilding execution heuristics and PIT validation if it still consumes option snapshots

Option expected-value ranking:

- should directly reuse current spread generation, execution adjustment, EV, and ranking components
- this is the fastest near-term extension path

Returns-based ML:

- in scope conceptually
- should be integrated through a clean signal/feature/result interface, not by forcing SEC/fundamental ML code into this repo

## 12. Relationship to Other Projects

Keep this repository focused on options/price/provenance/calibration research.

Do not merge unrelated research stacks into this repo just because they also produce alpha ideas. In particular:

- SEC / filing / fundamental ML should remain a separate system unless this repo acquires a direct runtime dependency on it
- future integration should happen through artifact-level interfaces such as features, signals, probabilities, or outcome/result joins
- returns-based ML is in scope for future collaboration, but it should remain clearly separate from SEC/fundamental ML concerns

The clean boundary to prefer is:

- separate data collection / model training systems
- shared downstream artifact contracts where evaluation or portfolio combination is needed

## 13. Recommended Next Uses

What can be built quickly now without a large platform rewrite:

1. Strict-snapshot options research notebooks that sweep `OfflineScanQualitySettings` and compare how filters, slippage penalties, or concentration caps change ranked candidates.
2. Alternative ranking notebooks that reuse current spread generation and EV outputs but test different ranking formulas or post-filters.
3. Calibration data assembly notebooks once trusted timestamped option snapshots are available.
4. Volatility / term-structure overlays that enrich `ScannerOpportunityRow` without rebuilding the core scanner.
5. Small returns-based ML notebooks that reuse PIT and evaluation discipline while staying outside the spread-construction core.

Likely duplication to avoid:

- rebuilding local option-chain loaders
- rebuilding point-in-time validation
- rebuilding same-snapshot historical manifest handling
- rebuilding spread-construction logic
- rebuilding prediction/outcome join keys
- rebuilding the current execution-adjustment heuristic
- rebuilding calibration validators and reliability metrics

The fastest immediate research path is not generalized platform work. It is a small notebook or module that reuses:

- `load_historical_snapshots(...)`
- `build_scanner_opportunities(...)`
- `export_scanner_probability_predictions(...)`
- `evaluate_probability_predictions(...)`

and adds only new signal logic or ranking research on top.

## 14. Machine-Readable Quick Reference

```yaml
project_name: options_edge_scanner
as_of_date: 2026-08-17
project_role: >
  Offline research foundation for deterministic debit vertical spread screening,
  point-in-time validation, and calibration-contract workflows from local option snapshots.
maturity:
  scanner: strong_offline_foundation
  calibration_contracts: implemented
  historical_manifest_research: implemented_but_narrow
  backtesting: placeholder_only
  live_trading: not_implemented
canonical_entry_points:
  - options_edge_scanner.cli.offline_scan
  - options_edge_scanner.cli.offline_batch_scan
  - options_edge_scanner.cli.historical_snapshot_scan
  - options_edge_scanner.cli.export_probability_predictions
  - options_edge_scanner.cli.probability_calibration_eval
  - options_edge_scanner.cli.alpaca_realized_underlying_acquire
  - options_edge_scanner.cli.materialize_realized_outcomes
canonical_inputs:
  - OptionQuoteRow local CSV/parquet
  - strict HistoricalSnapshotManifestRow CSV/JSON
  - RealizedUnderlyingObservationRow CSV
canonical_outputs:
  - ScannerOpportunityRow CSV
  - scan report JSON
  - ProbabilityPredictionRow CSV
  - RealizedOutcomeRow CSV
  - calibration summary / bins / joined observations CSVs
key_modules:
  - options_edge_scanner.data.loader
  - options_edge_scanner.data.provenance
  - options_edge_scanner.data.historical_snapshot_loader
  - options_edge_scanner.scanner.engine
  - options_edge_scanner.scanner.spread_generator
  - options_edge_scanner.scanner.execution
  - options_edge_scanner.scanner.quality_filters
  - options_edge_scanner.scanner.opportunity_ranker
  - options_edge_scanner.models.probability_models
  - options_edge_scanner.models.spread_ev_calculator
  - options_edge_scanner.calibration.contracts
  - options_edge_scanner.calibration.evaluation
  - options_edge_scanner.calibration.materialization
key_schemas:
  - OptionQuoteRow
  - HistoricalSnapshotManifestRow
  - VerticalSpreadRow
  - ScannerOpportunityRow
  - ProbabilityPredictionRow
  - RealizedUnderlyingObservationRow
  - RealizedOutcomeRow
reusable_utilities:
  - load_option_quotes
  - enrich_option_quote_provenance
  - validate_point_in_time_integrity
  - load_historical_snapshots
  - generate_vertical_spreads
  - apply_execution_adjustments
  - calculate_expected_value
  - predict_spread_probability
  - build_scanner_opportunities
  - export_scanner_probability_predictions
  - evaluate_probability_predictions
risk_layer:
  enforced:
    - quote_provenance_required_by_default
    - lookahead_rejection
    - strict_same_timestamp_historical_snapshots
    - quote_and_spread_quality_filters
    - optional_ticker_and_expiration_concentration_caps
    - calibration_leakage_checks
  missing:
    - position_sizing
    - drawdown_limits
    - kill_switches
    - live_exposure_controls
integration_contract:
  consume:
    - OptionQuoteRow for raw options work
    - ScannerOpportunityRow for ranked-candidate work
    - ProbabilityPredictionRow and RealizedOutcomeRow for evaluation work
  preserve:
    - snapshot_id
    - quote_observed_at
    - as_of
    - explicit_predicted_event_semantics
  promote:
    - notebook_or_module
    - deterministic_artifacts
    - tests
    - CLI_if_stable
current_blockers:
  - no_trusted_repo_local_point_in_time_option_snapshot_source
  - stale_repo_local_yahoo_sidecars_missing_snapshot_id
  - no_meaningful_empirical_calibration_dataset
  - no_real_backtester
non_reusable_placeholders:
  - options_edge_scanner.models.pricing
  - options_edge_scanner.signals.generator
  - options_edge_scanner.utils.logger
  - options_edge_scanner.backtest.runner_as_true_backtester
legacy_or_stale:
  - run_scanner.py_retired
  - outputs/offline_scan_sample.csv_not_calibration_ready
  - outputs/closeout_audit/offline_scan_predictions.csv_stale
  - outputs/yahoo_option_chains_sidecars_missing_snapshot_id
recommended_immediate_next_step: >
  Acquire or build a strict timestamped historical option-snapshot corpus, then
  reuse the existing scanner -> prediction export -> outcome materialization ->
  calibration pipeline instead of adding new platform layers first.
```
