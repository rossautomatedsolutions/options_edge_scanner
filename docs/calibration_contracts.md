# Probability Calibration Contracts

This repo now includes a research-only probability calibration framework for the maintained offline scanner.
The framework is designed to preserve exact event semantics, keep predictions separate from realized outcomes, and enforce forward-only evaluation rules.

## Baseline Event Semantics

The current maintained scanner exports one explicit probability-model contract:

| Field | Current baseline value |
| --- | --- |
| `probability_model_name` | `lognormal_breakeven` |
| `probability_model_version` | `1` |
| `predicted_event_name` | `terminal_underlying_crosses_spread_breakeven` |
| `predicted_event_horizon` | `expiration` |

For the maintained debit vertical scanner path:

- `bull_call_debit` predicts whether terminal underlying price is strictly above `lower_strike + debit`
- `bear_put_debit` predicts whether terminal underlying price is strictly below `upper_strike - debit`

The calibration evaluator does not reinterpret this as trade PnL, max-profit touch, or any looser success proxy.
It recomputes the realized binary event from the exact exported threshold, direction, operator, and horizon.

## SPY Terminal Outcome Convention

The current bounded empirical scope is explicitly SPY only.
The repo-local historical SPY artifacts inspected for this slice are:

- `outputs/yahoo_option_chains/SPY_2026-06-15_yahoo.csv` with sidecar timestamp `2026-06-13T18:58:08.268431Z`
- `outputs/yahoo_option_chains/SPY_2026-07-17_yahoo.csv` with sidecar timestamp `2026-06-14T12:55:31.874815Z`

These local artifacts are useful for expiration inventory and contract semantics.
They are not yet strict historical snapshot inputs for calibration because the Yahoo sidecars record fetch time rather than a trusted option-quote timestamp.

The expirations represented by the local files above are:

- Monday, June 15, 2026
- Friday, July 17, 2026

Adopted terminal observation policy for these SPY expiration-horizon predictions:

| Field | Adopted value |
| --- | --- |
| underlying scope | `SPY` only |
| event horizon | `expiration` |
| terminal-price convention | `spy_expiration_day_close_proxy` |
| terminal-price convention version | `1` |
| observation timestamp | expiration-date `16:00:00` America/New_York, stored as explicit UTC |
| observed price field | underlying `close` |
| default underlying source | Alpaca `stocks.bars.v2` |
| default timeframe | `1Day` |
| default adjustment mode | `raw` |
| required feed choice | explicit, not implicit |

Research interpretation:

- the realized event is resolved from an explicit SPY expiration-date 4:00 p.m. America/New_York close timestamp plus a provider-sourced end-of-day close proxy
- for the two local artifacts above, that means `2026-06-15T20:00:00Z` and `2026-07-17T20:00:00Z`
- this policy is implemented explicitly in `options_edge_scanner.calibration.terminal_semantics`
- unsupported tickers raise rather than silently reusing the SPY rule

Known difference versus full option-settlement mechanics:

- SPY options are American-style and physically settled into ETF shares
- this research proxy intentionally resolves the terminal underlying event from an expiration-day close proxy only
- the Alpaca daily-bar close is not claimed to be the official closing-auction print
- it does not model contrary exercise instructions, assignment choice, or post-close share exposure

## ProbabilityPredictionRow

`ProbabilityPredictionRow` is the prediction-side artifact exported from safe scanner opportunity rows through `options_edge_scanner.calibration.export_scanner_probability_predictions(...)`.

Identity and timing fields:

| Column | Type | Notes |
| --- | --- | --- |
| `prediction_id` | string | Stable identifier derived from observation group, spread structure, and probability-model version. |
| `snapshot_id` | string | Logical snapshot identifier carried from quote provenance. |
| `ticker` | string | Underlying symbol, normalized to uppercase. |
| `prediction_timestamp` | full ISO-8601 timestamp with timezone | When the probability prediction became observable. Safe scanner export uses the later of `quote_observed_at` and `as_of` so prediction timing cannot predate the evaluation bound that changed DTE. |
| `quote_observed_at` | full ISO-8601 timestamp with timezone | Quote snapshot timestamp used by the prediction. |
| `as_of` | full ISO-8601 timestamp with timezone | Effective evaluation bound used during scanner ranking. |
| `expiration` | `YYYY-MM-DD` | Event horizon date. |

Spread structure fields:

| Column | Type | Notes |
| --- | --- | --- |
| `spread_type` | string | Current maintained scanner emits `bull_call_debit` or `bear_put_debit`. |
| `lower_strike` | float | Lower strike in the vertical. |
| `upper_strike` | float | Upper strike in the vertical. |
| `long_strike` | float | Long leg strike. |
| `short_strike` | float | Short leg strike. |

Probability semantics fields:

| Column | Type | Notes |
| --- | --- | --- |
| `predicted_probability` | float in `[0, 1]` | Probability assigned to the exact exported event. |
| `probability_model_name` | string | Versioned model family name. |
| `probability_model_version` | string | Model contract version. |
| `predicted_event_name` | string | Current evaluator supports `terminal_underlying_crosses_spread_breakeven`. |
| `predicted_event_direction` | string | `above` or `below`. |
| `predicted_event_operator` | string | `>` or `<`, consistent with direction. |
| `predicted_event_threshold` | float | Exact terminal underlying threshold used by the model. |
| `predicted_event_horizon` | string | Current baseline uses `expiration`. |

Outcome-linkage fields:

| Column | Type | Notes |
| --- | --- | --- |
| `required_outcome_horizon` | string | Horizon required from the future outcome artifact. |
| `required_outcome_key` | string | Stable join key: `TICKER|EXPIRATION|HORIZON|MEASURE`, validated against the row fields. |
| `observation_group_id` | string | Correlation-group identifier for same-snapshot related predictions, validated from `snapshot_id`, `ticker`, `prediction_timestamp`, and `expiration`. |

Optional provenance fields preserved when present:

| Column | Type | Notes |
| --- | --- | --- |
| `snapshot_source` | string | Snapshot provenance label. |
| `input_path` | string | Local source artifact path. |
| `source_metadata_path` | string | Sidecar metadata path. |

## RealizedUnderlyingObservationRow

`RealizedUnderlyingObservationRow` is the provider-neutral local artifact consumed by outcome materialization.
It is normalized from provider responses before any `RealizedOutcomeRow` is built.

Required fields include:

- contract linkage: `observation_id`, `required_outcome_key`, `ticker`, `event_date`, `required_outcome_horizon`, `realized_outcome_measure`
- terminal-price semantics: `terminal_price_convention`, `terminal_price_convention_version`, `price_field`, `observed_market_session`
- observed value: `observed_price`, `observed_at`, `market_close_timestamp`
- source provenance: `source`, `source_dataset`, `source_feed`, `timeframe`, `adjustment_mode`, `acquired_at`, `provenance_artifact_id`

Optional audit fields currently preserved when present:

- `source_bar_timestamp`
- `provider_symbol`
- `currency`

Validation rules include:

- `required_outcome_key` must match the row's own ticker, event date, horizon, and measure fields
- `observed_at` must equal the explicit policy market-close timestamp for the row's ticker and horizon
- `market_close_timestamp` and `observed_at` must fall on `event_date`
- `acquired_at` must be on or after `observed_at`
- duplicate `required_outcome_key` values are rejected to prevent ambiguous future-outcome matching
- unsupported tickers fail fast rather than inheriting the SPY convention

## RealizedOutcomeRow

`RealizedOutcomeRow` is the separate future-outcome artifact used for scoring.

| Column | Type | Notes |
| --- | --- | --- |
| `outcome_id` | string | Unique realized-outcome identifier. |
| `required_outcome_key` | string | Must match exactly one logical future outcome. |
| `ticker` | string | Underlying symbol, uppercase. |
| `expiration` | `YYYY-MM-DD` | Expiration aligned with the prediction contract. |
| `required_outcome_horizon` | string | Horizon label, currently `expiration`. |
| `realized_outcome_measure` | string | Currently must equal `terminal_underlying_price`. |
| `realized_terminal_underlying_price` | float | Terminal underlying reference used to resolve the realized event. |
| `realized_outcome_observed_at` | full ISO-8601 timestamp with timezone | When the realized outcome became observable. |
| `realized_outcome_source` | string | Short provenance label for the realized outcome artifact. |

`required_outcome_key` must be unique in the realized-outcome artifact and must match the row's own ticker, expiration, horizon, and measure fields.
One future outcome row represents one expiration-level realized measurement.

Outcome materialization currently preserves additional audit fields when present:

- `realized_underlying_observation_id`
- `terminal_price_convention`
- `terminal_price_convention_version`
- `observed_market_session`
- `market_close_timestamp`
- `source_dataset`
- `source_feed`
- `adjustment_mode`
- `provenance_artifact_id`
- `source_snapshot_count`
- `source_snapshot_ids`

## Joined Evaluation Outputs

`evaluate_probability_predictions(...)` returns three machine-readable artifacts plus one concise summary string.

Joined observation artifact:

- one row per prediction joined to one realized outcome
- preserves prediction identity, timing, spread structure, model/version, event semantics, optional prediction provenance, and realized outcome provenance
- adds:
  - `realized_event`
  - `outcome_key_prediction_count`
  - `probability_error`
  - `absolute_error`
  - `squared_error`

Reliability-bin artifact:

| Column | Meaning |
| --- | --- |
| `bin_index` | Zero-based fixed-width bin index on `[0, 1]` |
| `bin_lower` / `bin_upper` | Bin edges |
| `bin_label` | Human-readable interval label |
| `prediction_count` | Number of predictions in the bin |
| `event_count` | Number of realized events in the bin |
| `mean_predicted_probability` | Average predicted probability in the bin |
| `observed_event_rate` | Empirical event frequency in the bin |
| `calibration_gap` | `mean_predicted_probability - observed_event_rate` |
| `absolute_calibration_gap` | Absolute gap |

Calibration summary artifact:

| Column | Meaning |
| --- | --- |
| `prediction_count` | Total evaluated predictions |
| `outcome_count` | Distinct realized outcomes joined |
| `overall_event_rate` | Mean realized event rate |
| `mean_predicted_probability` | Mean predicted probability |
| `brier_score` | Mean squared probability error |
| `log_loss` | Safely clipped log loss |
| `expected_calibration_error` | Weighted mean absolute bin gap |
| `maximum_calibration_error` | Worst non-empty bin gap |
| `empty_bin_count` | Number of empty reliability bins |
| `non_empty_bin_count` | Number of populated bins |
| `shared_outcome_key_count` | Number of outcome keys reused by multiple predictions |
| `max_predictions_per_outcome_key` | Largest prediction count mapped to one outcome key |

## Leakage Controls

The calibration framework enforces the following controls:

- predictions and realized outcomes are separate artifacts with separate validators
- prediction and outcome timestamps must be full ISO-8601 timestamps with explicit timezone
- `prediction_timestamp` must be on or after `quote_observed_at`
- `prediction_timestamp` must be on or after `as_of`
- `expiration`-horizon predictions are rejected on the expiration date itself because the current contract does not carry an explicit event-resolution timestamp
- `realized_outcome_observed_at` must be on or after expiration
- `realized_outcome_observed_at` must be strictly later than both `prediction_timestamp` and `quote_observed_at`
- ticker, expiration, and required-outcome horizon must match exactly across the join
- `required_outcome_key` and `observation_group_id` are validated against the row fields rather than treated as opaque strings
- duplicate semantic predictions are rejected even if their IDs differ
- multiple predictions sharing one `required_outcome_key` are rejected by default because they are correlated; callers must opt in explicitly
- forward evaluation helpers are time-aware only: fixed holdout, expanding, and rolling
- the framework intentionally does not provide random split defaults

## CLI Surface

The offline evaluation CLI reads prediction and outcome CSVs and writes machine-readable results:

```powershell
python -m options_edge_scanner.cli.probability_calibration_eval `
  --predictions tests/fixtures/sample_probability_predictions.csv `
  --outcomes tests/fixtures/sample_realized_outcomes.csv `
  --summary-output outputs/calibration_summary.csv `
  --bins-output outputs/calibration_bins.csv `
  --observations-output outputs/calibration_observations.csv
```

CLI outputs:

- summary CSV
- reliability-bin CSV
- optional joined-observations CSV
- concise human-readable summary printed to stdout

Realized underlying acquisition and outcome materialization CLIs:

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

## Current Boundary

What is implemented now:

- explicit prediction and realized-outcome contracts
- explicit SPY terminal-price semantics for expiration-horizon research
- provider-neutral realized underlying observations
- Alpaca stock-bar normalization into the local realized-underlying contract
- strict outcome materialization from historical snapshot manifests plus normalized underlying artifacts
- safe export from maintained scanner opportunities into prediction artifacts
- deterministic forward-only evaluation helpers
- machine-readable calibration outputs and concise text summaries
- fixture and synthetic regression coverage for edge cases, timestamp leakage, shared outcomes, and adversarial probabilities

What is not implemented yet:

- a broad empirical prediction/outcome dataset suitable for serious calibration measurement
- an empirically calibrated replacement for the current `lognormal_breakeven` baseline
- random-split model selection workflows
- a real options lifecycle backtester or execution simulator

The next prerequisite for empirical calibration work is dataset acquisition and normalization, not a new backtester surface.
