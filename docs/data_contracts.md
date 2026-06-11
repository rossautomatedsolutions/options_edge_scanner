# Data Contracts

This repo uses three canonical dataframe row contracts for the research-only vertical spread scanner foundation. The goal is deterministic, inspectable analysis rather than live trading behavior.

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
| `mid` | float | Midpoint used for deterministic offline tests and spread construction. |
| `implied_vol` | float | Annualized implied volatility as a decimal. |
| `underlying_price` | float | Underlying spot reference used for spread probability estimation. |

Normalization rules:

- `mid = (bid + ask) / 2` when not supplied directly.
- `type` is normalized to lowercase `call` / `put`.
- `expiration` is parsed to a timestamp.
- Numeric fields are coerced with invalid values becoming `NaN`.

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
| `implied_volatility` | float | Mean IV across both legs. |
| `underlying_price` | float | Mean underlying spot across both legs. |

Spread construction rules:

- `bull_call_debit`: long lower-strike call, short upper-strike call.
- `bear_put_debit`: long upper-strike put, short lower-strike put.
- Only same-ticker, same-expiration pairs are valid.
- Width must be positive and at most 10 strike points in the current foundation.
- `0 < debit < width`.

## ScannerOpportunityRow

Ranked scanner output row produced by `build_scanner_opportunities`.

Required columns:

| Column | Type | Notes |
| --- | --- | --- |
| All `VerticalSpreadRow` columns | mixed | Preserved from the generated spread row. |
| `days_to_expiration` | float | Positive days between `as_of` date and expiration. |
| `probability_of_profit` | float | Canonical PoP field from `estimate_probability_of_profit`. |
| `probability` | float | Alias for `probability_of_profit` for compatibility. |
| `prob_loss` | float | `1 - probability_of_profit`. |
| `expected_value` | float | Net EV after transaction-cost adjustment. |
| `EV` | float | Alias for `expected_value` for compatibility. |
| `edge_pct` | float | EV divided by max loss, in percent. |
| `ev_method` | string | Current method: `breakeven_binary_mvp`. |
| `avg_profit` | float | Current binary EV average winning payoff assumption. |
| `avg_loss` | float | Current binary EV average losing payoff assumption. |

Ranking rules:

- Keep only rows with `expected_value > 0`.
- Keep only rows with `probability_of_profit > 0.3`.
- Sort by `expected_value` descending, then `edge_pct` descending.
- Return the top 20 rows.

Boundary:

- These contracts are for research, education, and decision support only.
- They are not trade instructions, recommendations, routing messages, or brokerage objects.

## Offline Adapter

The first offline adapter lives in [loader.py](/C:/GitHub/options_edge_scanner/options_edge_scanner/data/loader.py).
The config-driven offline scan entrypoint lives in [offline_scan.py](/C:/GitHub/options_edge_scanner/options_edge_scanner/cli/offline_scan.py).
The batch manifest entrypoint lives in [offline_batch_scan.py](/C:/GitHub/options_edge_scanner/options_edge_scanner/cli/offline_batch_scan.py).

Current behavior:

- reads local `.csv` files
- reads local `.parquet` files when pandas parquet support is already available
- validates required `OptionQuoteRow` columns before scanner use
- applies only safe alias normalization already consistent with repo conventions
- returns a dataframe compatible with `build_scanner_opportunities(...)`
- can write ranked `ScannerOpportunityRow` output to a local CSV artifact without fetching live data
- can batch multiple offline scans from a manifest with `input_path`, `output_path`, and explicit `as_of`
- can optionally emit a batch summary CSV with `input_path`, `output_path`, `as_of`, `status`, `row_count`, and `error_message`

Documented alias coverage currently exercised by repo tests includes:

- `option_type -> type`
- `expiry -> expiration`
- `strike_price -> strike`
- `iv -> implied_vol`

The loader also supports additional low-risk aliases present in the implementation, including:

- `expiry_date -> expiration`
- `expiration_date -> expiration`
- `implied_volatility -> implied_vol`

Batch manifest path behavior currently exercised by repo tests:

- manifest row paths are interpreted exactly as provided
- manifest row paths work when the current working directory resolves them
- manifest row paths are not implicitly resolved relative to the manifest file location

Operational notes:

- These CLI entrypoints are offline and fixture-driven only.
- They do not place orders, connect to a broker, fetch live market data, or emit trading recommendations.
- Expected input files are local option-quote `.csv` files, or `.parquet` when pandas parquet support is already installed.
- Output files are generated CSV artifacts written to the caller-provided `--output` path or manifest `output_path`. The repo-level `outputs/` directory is intended for generated local artifacts and should remain untracked.
