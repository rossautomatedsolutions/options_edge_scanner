# Data Contracts

This repo uses a small set of canonical dataframe row contracts for the research-only offline vertical spread scanner. The goal is deterministic, inspectable analysis rather than live trading behavior.

## OptionQuoteRow

Normalized single-option quote row used as scanner input.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `ticker` | string | Underlying symbol, uppercase preferred. |
| `expiration` | datetime-like | Option expiration date. |
| `strike` | float | Contract strike price. |
| `type` | string | `call` or `put`. |
| `bid` | float | Bid quote. |
| `ask` | float | Ask quote. |
| `mid` | float | Optional on raw input; the normalized loader derives it from `(bid + ask) / 2` when absent. |
| `implied_vol` | float | Annualized implied volatility as a decimal. |
| `underlying_price` | float | Underlying spot reference used for spread probability estimation. |

Optional provenance columns:

| Column | Type | Notes |
| --- | --- | --- |
| `snapshot_id` | string | Logical snapshot identity when a strict historical manifest supplied it. |
| `snapshot_source` | string | Snapshot-level source label such as `yahoo_finance` or `fixture.vendor`. |
| `quote_observed_at` | datetime-like | When the option snapshot was observed or fetched. |
| `underlying_price_observed_at` | datetime-like | When the carried spot reference was observed. |
| `underlying_price_source` | string | Short provenance label such as `history.close` or `fixture.snapshot`. |
| `input_path` | string | Local source file path when the CLI enriched it. |
| `source_metadata_path` | string | Sidecar metadata path when present. |

Normalization rules:

- `mid = (bid + ask) / 2` when not supplied directly.
- `type` is normalized to lowercase `call` / `put`.
- `expiration` is parsed to a timestamp.
- Numeric fields are coerced with invalid values becoming `NaN`.
- Known provenance timestamps are parsed to pandas timestamps when present.

Point-in-time rule:

- The maintained scanner path requires `quote_observed_at` provenance by default.
- date-only `as_of` values are treated as day-level bounds.
- timestamp-valued `as_of` inputs are checked at full timestamp precision.
- `as_of` must not predate `quote_observed_at` under the applicable precision.
- `underlying_price_observed_at` is also checked when present.
- `--allow-unsafe-as-of` is the explicit escape hatch for ad hoc legacy inputs.
- when `--spot` overrides `underlying_price`, the maintained CLI expects `--spot-observed-at` for safe provenance; otherwise it clears inherited spot provenance and requires `--allow-unsafe-as-of`

## VerticalSpreadRow

Canonical research spread row emitted by `generate_vertical_spreads`.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `ticker` | string | Underlying symbol. |
| `expiration` | datetime-like | Shared expiration for both legs. |
| `option_type` | string | `call` or `put`, describing the leg family. |
| `spread_type` | string | Canonical spread label: `bull_call_debit` or `bear_put_debit`. |
| `lower_strike` | float | Lower strike in the vertical. |
| `upper_strike` | float | Upper strike in the vertical. |
| `long_strike` | float | Long-leg strike. |
| `short_strike` | float | Short-leg strike. |
| `width` | float | `upper_strike - lower_strike`. |
| `debit` | float | Net debit paid for the spread. |
| `cost` | float | Alias for `debit` kept for compatibility. |
| `max_profit` | float | `width - debit`. |
| `max_loss` | float | Equal to `debit` for debit spreads. |
| `long_bid` / `long_ask` / `long_mid` | float | Long-leg quote inputs preserved for later execution diagnostics. |
| `short_bid` / `short_ask` / `short_mid` | float | Short-leg quote inputs preserved for later execution diagnostics. |
| `long_volume` / `short_volume` | float | Optional size fields carried from the legs when available. |
| `long_open_interest` / `short_open_interest` | float | Optional OI fields carried from the legs when available. |
| `long_delta` / `short_delta` | float | Optional delta fields carried from the legs when available. |
| `implied_volatility` | float | Mean IV across both legs. |
| `underlying_price` | float | Shared underlying spot carried from the legs. |

Propagated provenance columns when present:

- `snapshot_id`
- `snapshot_source`
- `quote_observed_at`
- `underlying_price_observed_at`
- `underlying_price_source`
- `input_path`
- `source_metadata_path`

Spread construction rules:

- `bull_call_debit`: long lower-strike call, short upper-strike call.
- `bear_put_debit`: long upper-strike put, short lower-strike put.
- Only same-ticker, same-expiration, same-provenance leg pairs are valid.
- Width must be positive and at most 10 strike points in the current foundation.
- `0 < debit < width`.
- Spread legs must share a consistent `underlying_price` snapshot.

## ScannerOpportunityRow

Ranked scanner output row produced by `build_scanner_opportunities`.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| All `VerticalSpreadRow` columns | mixed | Preserved from the generated spread row. |
| `as_of` | datetime-like | Effective evaluation date used for DTE and point-in-time checks. |
| `days_to_expiration` | float | Positive days between `as_of` date and expiration. |
| `probability_model_name` | string | Current baseline export name: `lognormal_breakeven`. |
| `probability_model_version` | string | Current baseline export version: `1`. |
| `predicted_event_name` | string | Exact event name associated with the probability field. |
| `predicted_event_direction` | string | `above` or `below`. |
| `predicted_event_operator` | string | `>` or `<`, consistent with direction. |
| `predicted_event_threshold` | float | Exact terminal underlying threshold represented by the probability field. |
| `predicted_event_horizon` | string | Current maintained scanner uses `expiration`. |
| `probability_of_profit` | float | Canonical PoP field from `estimate_probability_of_profit`. |
| `probability` | float | Alias for `probability_of_profit` for compatibility. |
| `prob_loss` | float | `1 - probability_of_profit`. |
| `quoted_debit` / `quoted_cost` | float | Original midpoint-based debit/cost before execution adjustment. |
| `quoted_max_profit` / `quoted_max_loss` | float | Original midpoint-based payoff bounds before execution adjustment. |
| `spread_bid` / `spread_ask` | float | Net spread market derived from long-leg and short-leg bid/ask quotes when available. |
| `spread_market_width` | float | `spread_ask - spread_bid` when executable spread quotes are available. |
| `entry_slippage` | float | Conservative entry penalty added above midpoint for the maintained research execution model. |
| `entry_slippage_pct` | float | `entry_slippage / quoted_debit` when `quoted_debit > 0`. |
| `entry_fill_fraction_of_market_width` | float | Fraction of the quoted spread market width used to penalize midpoint entry. |
| `entry_price_policy` | string | Current policy label, such as `mid_plus_dynamic_market_width_penalty`. |
| `liquidity_score` | float | 0..1 execution-liquidity score derived from quoted width and optional size fields. |
| `spread_min_volume` / `spread_min_open_interest` | float | Minimum size fields across both legs when available. |
| `theoretical_expected_value` | float | Midpoint-theoretical EV before execution adjustment. |
| `theoretical_edge_pct` | float | Midpoint-theoretical EV divided by midpoint max loss, in percent. |
| `theoretical_ev_method` | string | EV method label used for the midpoint-theoretical calculation. |
| `expected_value` | float | Execution-adjusted EV after transaction-cost adjustment. |
| `EV` | float | Alias for `expected_value` for compatibility. |
| `edge_pct` | float | Execution-adjusted EV divided by execution-adjusted max loss, in percent. |
| `ev_method` | string | Current method: `lognormal_vertical_exact`. |
| `avg_profit` | float | Conditional expected PnL given the trade finishes profitable under the current EV method. |
| `avg_loss` | float | Conditional expected PnL given the trade does not finish profitable under the current EV method. |
| `ranking_score` | float | Execution-aware ranking score used by the maintained selector. |
| `selection_rank` | integer | 1-based selection order after ranking and optional concentration caps. |

Ranking rules:

- Keep only rows above the configured `min_expected_value` and `min_probability_of_profit` thresholds.
- Compute `ranking_score = expected_value * (0.5 + 0.5 * liquidity_score)` for rows that survive the filters.
- Sort by `ranking_score`, then `expected_value`, `edge_pct`, `probability`, `liquidity_score`, and deterministic structure fields.
- Return at most the configured `top_n` rows.
- Optionally enforce concentration caps by ticker and expiration.

Boundary:

- These contracts are for research, education, and decision support only.
- They are not trade instructions, recommendations, routing messages, or brokerage objects.

Calibration export note:

- safe scanner outputs preserve the exact probability-model metadata and event semantics required for calibration export
- `options_edge_scanner.calibration.export_scanner_probability_predictions(...)` converts safe scanner output into `ProbabilityPredictionRow`
- unsafe ad hoc scans that lack quote provenance are intentionally not calibration-ready

## HistoricalSnapshotManifestRow

Strict manifest row used by `options_edge_scanner.cli.historical_snapshot_scan`.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| `snapshot_id` | string | Unique logical snapshot identifier. Duplicate IDs are rejected. |
| `ticker` | string | Underlying symbol for the entire logical snapshot. |
| `as_of` | datetime-like or `YYYY-MM-DD` | Research evaluation bound for that snapshot. |
| `chain_path` | string | Local option-chain artifact path. Relative paths resolve from the manifest directory. |
| `metadata_path` | string | Local sidecar metadata path. Relative paths resolve from the manifest directory. |

Optional cross-check columns:

| Column | Type | Notes |
| --- | --- | --- |
| `snapshot_source` | string | Snapshot-level source label. Must match metadata when both are present. |
| `quote_observed_at` | datetime-like | Explicit quote observation timestamp. Must match metadata/chain provenance when present. |
| `underlying_price` | float | Explicit spot/reference price for the snapshot. Must match metadata/chain provenance when present. |
| `underlying_price_observed_at` | datetime-like | Explicit spot observation timestamp. Must match metadata/chain provenance when present. |
| `underlying_price_source` | string | Explicit spot provenance label. Must match metadata/chain provenance when present. |
| `expiration_start` | datetime-like | Optional lower expiration bound covered by the artifact. |
| `expiration_end` | datetime-like | Optional upper expiration bound covered by the artifact. |

Loader rules:

- one row equals one logical symbol/snapshot record
- `snapshot_id` must be unique across the manifest
- `chain_path` and `metadata_path` are resolved deterministically relative to the manifest location
- the loader rejects duplicate resolved chain artifacts and duplicate resolved metadata artifacts
- the strict historical path expects the metadata sidecar to carry `snapshot_id`; manifest-only snapshot IDs are insufficient
- `quote_observed_at`, `underlying_price`, `underlying_price_observed_at`, `underlying_price_source`, and `snapshot_source` must come from explicit manifest fields, explicit metadata fields, or both
- when both manifest and metadata provide the same provenance field, they must agree exactly
- the loader fills missing chain-level provenance from the explicit manifest/metadata contract only; it does not infer timestamps or spot values from filenames or runtime state
- `ticker` must match the chain artifact and metadata ticker when metadata includes one
- `as_of` must not predate the observed quote snapshot or spot observation under the same day/timestamp precision rules used by the maintained offline scanner

Same-snapshot pairing rule:

- the strict historical path requires `quote_observed_at == underlying_price_observed_at`
- if the option chain and the spot reference cannot prove they came from the same logical observation timestamp, the snapshot is rejected
- matching calendar date alone is insufficient

Forbidden inference:

- no implicit snapshot ID derivation from filenames or directories
- no implicit metadata-sidecar reuse across multiple logical snapshots
- no implicit relative-path resolution against the current working directory
- no unsafe historical bypass analogous to `--allow-unsafe-as-of`

## Probability Calibration Artifacts

The maintained offline scanner can now feed a research-only calibration workflow.
The detailed narrative contract lives in [calibration_contracts.md](calibration_contracts.md).

### ProbabilityPredictionRow

Prediction-side artifact exported from safe scanner opportunities.

Required fields include:

- identity and timing: `prediction_id`, `snapshot_id`, `ticker`, `prediction_timestamp`, `quote_observed_at`, `as_of`, `expiration`
- spread structure: `spread_type`, `lower_strike`, `upper_strike`, `long_strike`, `short_strike`
- probability semantics: `predicted_probability`, `probability_model_name`, `probability_model_version`, `predicted_event_name`, `predicted_event_direction`, `predicted_event_operator`, `predicted_event_threshold`, `predicted_event_horizon`
- outcome linkage: `required_outcome_horizon`, `required_outcome_key`, `observation_group_id`

Optional provenance fields preserved when present:

- `snapshot_source`
- `input_path`
- `source_metadata_path`

Validation rules include:

- timestamps must be full ISO-8601 values with explicit timezone
- `prediction_timestamp >= quote_observed_at`
- `prediction_timestamp >= as_of`
- `expiration`-horizon predictions must be observed before the expiration date
- probabilities must stay within `[0, 1]`
- `required_outcome_key` and `observation_group_id` must match the row's own contract fields
- duplicate semantic predictions are rejected even if their identifiers differ

### RealizedOutcomeRow

Separate future-outcome artifact joined to predictions by `required_outcome_key`.

Required fields:

- `outcome_id`
- `required_outcome_key`
- `ticker`
- `expiration`
- `required_outcome_horizon`
- `realized_outcome_measure`
- `realized_terminal_underlying_price`
- `realized_outcome_observed_at`
- `realized_outcome_source`

Validation rules include:

- `required_outcome_key` must be unique
- `required_outcome_key` must match the row's own ticker, expiration, horizon, and measure fields
- `realized_outcome_measure` must equal `terminal_underlying_price`
- `realized_outcome_observed_at` must be on or after expiration

### RealizedUnderlyingObservationRow

Provider-neutral local underlying observation artifact used before `RealizedOutcomeRow` materialization.

Required fields:

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

Optional audit fields currently preserved:

- `source_bar_timestamp`
- `provider_symbol`
- `currency`

Validation rules include:

- `required_outcome_key` must match the row's own ticker, event date, horizon, and measure fields
- `observed_at` must equal the explicit policy market-close timestamp for the row's ticker/horizon contract
- `market_close_timestamp` and `observed_at` must both fall on `event_date`
- `acquired_at` must be on or after `observed_at`
- duplicate `required_outcome_key` values are rejected
- unsupported tickers fail fast instead of inheriting the SPY convention silently

Current explicit terminal observation policy:

- scope: `SPY` only
- event horizon: `expiration`
- terminal underlying convention: `spy_expiration_day_close_proxy`
- stored observation timestamp: explicit UTC close timestamp such as `2026-06-15T20:00:00Z`
- default provider shape: Alpaca `stocks.bars.v2`, timeframe `1Day`, explicit `adjustment_mode`, explicit `source_feed`
- research boundary: the proxy resolves a close-based terminal underlying event only; it does not claim the provider close field is the official auction print, and it does not model contrary exercise instructions, assignment choice, or post-close share exposure

### Evaluation Artifacts

`evaluate_probability_predictions(...)` emits:

- joined observation rows that preserve prediction metadata, realized outcome provenance, and per-row errors
- fixed-width reliability bins with observed event rate and calibration gap
- one summary row with `brier_score`, `log_loss`, `expected_calibration_error`, `maximum_calibration_error`, event rate, and shared-outcome diagnostics

Leakage controls include:

- realized outcomes must be strictly later than both `prediction_timestamp` and `quote_observed_at`
- ticker, expiration, and horizon must match exactly across prediction and outcome artifacts
- shared `required_outcome_key` values across predictions are rejected by default because they represent correlated observations
- time-split helpers are forward-only: fixed holdout, expanding, and rolling

## Offline Adapter

The local-file adapter lives in [options_edge_scanner/data/loader.py](../options_edge_scanner/data/loader.py).
The provenance helpers live in [options_edge_scanner/data/provenance.py](../options_edge_scanner/data/provenance.py).
The config-driven offline scan entrypoint lives in [options_edge_scanner/cli/offline_scan.py](../options_edge_scanner/cli/offline_scan.py).
The batch manifest entrypoint lives in [options_edge_scanner/cli/offline_batch_scan.py](../options_edge_scanner/cli/offline_batch_scan.py).
The strict historical manifest entrypoint lives in [options_edge_scanner/cli/historical_snapshot_scan.py](../options_edge_scanner/cli/historical_snapshot_scan.py).

Current behavior:

- reads local `.csv` files
- reads local `.parquet` files when pandas parquet support is already available
- validates required `OptionQuoteRow` columns before scanner use
- applies safe alias normalization already consistent with repo conventions
- enriches provenance from a sibling `.meta.json` sidecar when available
- writes ranked `ScannerOpportunityRow` CSV artifacts without fetching live data
- batches multiple offline scans from a manifest with `input_path`, `output_path`, and explicit `as_of`
- can optionally emit a batch summary CSV with `input_path`, `output_path`, `as_of`, `status`, `row_count`, and `error_message`
- scans strict historical manifests one snapshot at a time, preserves snapshot provenance in every candidate row, and emits per-snapshot success/failure accounting
- resolves historical manifest artifact paths relative to the manifest file rather than to the current working directory
- refuses historical snapshots that attempt to combine option quotes and spot provenance from different observation timestamps
- can normalize Alpaca historical stock bars into `RealizedUnderlyingObservationRow` CSV artifacts
- can materialize strict `RealizedOutcomeRow` CSV artifacts from historical snapshot manifests plus normalized realized underlying artifacts

Documented alias coverage exercised by repo tests includes:

- `option_type -> type`
- `expiry -> expiration`
- `strike_price -> strike`
- `iv -> implied_vol`

The loader also supports additional low-risk aliases present in the implementation, including:

- `expiry_date -> expiration`
- `expiration_date -> expiration`
- `implied_volatility -> implied_vol`

Batch manifest path behavior currently exercised by repo tests:

- batch `input_path` and `output_path` are resolved relative to the manifest file location
- absolute batch paths are preserved as-is
- the batch path contract now matches the historical snapshot manifest contract more closely for main-machine handoff

Historical manifest path behavior exercised by repo tests:

- relative `chain_path` and `metadata_path` values are resolved relative to the manifest file location
- duplicate resolved artifact paths are rejected
- output provenance keeps relative/stable artifact references when the manifest supplied them

Operational notes:

- These CLI entrypoints are offline and fixture-driven only.
- They do not place orders, connect to a broker, or emit trading recommendations.
- Expected input files are local option-quote `.csv` files, or `.parquet` when pandas parquet support is already installed.
- The optional Yahoo ingestion command can generate those local files, but the scanner itself still consumes local artifacts only.
- Output files are generated CSV artifacts written to the caller-provided `--output` path or manifest `output_path`. The repo-level `outputs/` directory is intended for generated local artifacts and should remain untracked.
- A collection of strict historical snapshots is still not a complete backtest dataset. It does not by itself model survivorship, fills, slippage, liquidity, exits, or portfolio behavior.
