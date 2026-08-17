# Yahoo Option-Chain Ingestion Design

Historical note:
This design note predates the current implementation.
The implemented Yahoo snapshot utility now lives in `options_edge_scanner.yahoo_ingestion` and remains optional upstream artifact generation only.

## Status

Proposed only. This document defines an optional ingestion utility design for Yahoo Finance option-chain snapshots.

It does not approve implementation by itself.
It does not change scanner runtime behavior.
It does not allow scanner tests to use network access.

## Goal

Add an optional command that can fetch a Yahoo Finance option chain for one ticker and one expiration date, normalize the response into the existing `OptionQuoteRow` contract, and write a local CSV artifact for the current offline scanner.

The scanner must continue to consume only local files.

## Non-Goals

This design does not introduce:

- live scanner behavior
- direct scanner market-data fetches
- broker integration
- order placement
- execution workflows
- recommendations
- strategy promotion
- network-dependent tests

## Current Boundary

The existing scanner path is intentionally offline and local-file driven:

- canonical input contract is documented in [data_contracts.md](/C:/GitHub/options_edge_scanner/docs/data_contracts.md)
- local-file adapter is [loader.py](/C:/GitHub/options_edge_scanner/options_edge_scanner/data/loader.py)
- offline CLI entrypoints are [offline_scan.py](/C:/GitHub/options_edge_scanner/options_edge_scanner/cli/offline_scan.py) and [offline_batch_scan.py](/C:/GitHub/options_edge_scanner/options_edge_scanner/cli/offline_batch_scan.py)
- fixture-backed tests verify deterministic scanner behavior without network access

Any Yahoo ingestion must remain an upstream artifact-generation step. The scanner should not call Yahoo, `yfinance`, or any online source at runtime.

## Proposed Command

Command name:

`python -m options_edge_scanner.cli.yahoo_option_chain_ingest`

Rationale:

- keeps the command clearly separate from the offline scanner commands
- makes the networked behavior explicit in the entrypoint name
- preserves the current pattern of thin, task-specific CLI modules under `options_edge_scanner/cli/`

## Proposed CLI Shape

Minimal shape:

```powershell
python -m options_edge_scanner.cli.yahoo_option_chain_ingest `
  --ticker AAPL `
  --expiration 2026-09-18
```

Recommended full shape:

```powershell
python -m options_edge_scanner.cli.yahoo_option_chain_ingest `
  --ticker AAPL `
  --expiration 2026-09-18 `
  --output outputs/yahoo_option_chains/AAPL/AAPL_2026-09-18_yahoo.csv `
  --cache-dir outputs/yahoo_option_chains/cache `
  --overwrite
```

Arguments:

- `--ticker`
  - required
  - underlying symbol to fetch
- `--expiration`
  - required
  - target option expiration in `YYYY-MM-DD`
- `--output`
  - optional
  - explicit destination CSV path for the normalized local artifact
- `--output-dir`
  - optional alternative to `--output`
  - when provided, command builds a deterministic filename under the directory
- `--cache-dir`
  - optional
  - directory for raw response cache artifacts and fetch metadata
- `--overwrite`
  - optional flag
  - required to replace an existing normalized output file
- `--use-cache`
  - optional flag
  - prefer an unexpired cached raw payload over a fresh fetch
- `--cache-ttl-seconds`
  - optional
  - default TTL for raw-response cache freshness
- `--write-raw-json`
  - optional flag
  - persist raw vendor payload metadata for provenance/debugging
- `--timeout-seconds`
  - optional
  - network timeout boundary for the vendor call

Not included initially:

- batch ticker ingestion
- scanner invocation
- auto-run of offline scan after ingest
- any flag that blurs the line between artifact generation and scanner runtime

## Dependency Choice

Primary choice:

- `yfinance` as an optional ingestion dependency

Rationale:

- it already aligns with the requested Yahoo Finance source
- it provides ticker expiration discovery and `option_chain(expiration)` access
- it is sufficient for a narrow research-only snapshot utility

Design requirement:

- `yfinance` must not be required for offline scanner usage or offline scanner tests

Recommended packaging posture:

- remove any unconditional `yfinance` import from the offline scanner path
- treat Yahoo ingestion as an optional dependency, for example through an extra such as `.[yahoo]`, or through a clearly documented manual install step
- fail with a clear message if the user invokes the Yahoo command without `yfinance` installed

Example failure text:

`Yahoo ingestion requires the optional 'yfinance' dependency. Install the Yahoo ingestion extras before running this command.`

## Output Folder Convention

Recommended normalized output root:

`outputs/yahoo_option_chains/`

Recommended normalized artifact pattern:

`outputs/yahoo_option_chains/{TICKER}/{TICKER}_{EXPIRATION}_yahoo.csv`

Examples:

- `outputs/yahoo_option_chains/AAPL/AAPL_2026-09-18_yahoo.csv`
- `outputs/yahoo_option_chains/SPY/SPY_2026-12-18_yahoo.csv`

Recommended cache root:

`outputs/yahoo_option_chains/cache/{TICKER}/`

Recommended cache artifact pattern:

- normalized CSV: `{TICKER}_{EXPIRATION}_yahoo.csv`
- raw metadata JSON: `{TICKER}_{EXPIRATION}_yahoo.meta.json`
- optional raw payload JSON: `{TICKER}_{EXPIRATION}_yahoo.raw.json`

Rationale:

- keeps generated ingestion artifacts under the existing untracked local-output convention
- separates human-consumable scanner input from cache/provenance files
- supports repeated offline scans against a stable local snapshot

## Raw Yahoo Fields

Expected `yfinance` option-chain fields available per side commonly include:

- `contractSymbol`
- `strike`
- `lastPrice`
- `bid`
- `ask`
- `change`
- `percentChange`
- `volume`
- `openInterest`
- `impliedVolatility`
- `inTheMoney`
- `contractSize`
- `currency`
- `lastTradeDate`

Underlying reference data from Yahoo should be captured separately from the chain rows, for example from ticker history or fast info:

- underlying close or last-trade proxy used as `underlying_price`
- fetch timestamp
- source ticker
- requested expiration

Design note:

- the normalized scanner CSV should include only the current `OptionQuoteRow` fields
- extra vendor-specific fields should go into sidecar metadata, not into scanner input, unless the repo later expands the canonical input contract through a separate reviewed contract change

## Normalized Scanner Fields

The generated CSV must match the current `OptionQuoteRow` contract exactly:

| Normalized column | Source |
| --- | --- |
| `ticker` | requested ticker, uppercased |
| `expiration` | requested expiration, parsed as date |
| `strike` | Yahoo `strike` |
| `type` | literal `call` for calls, `put` for puts |
| `bid` | Yahoo `bid` |
| `ask` | Yahoo `ask` |
| `mid` | computed as `(bid + ask) / 2.0` |
| `implied_vol` | Yahoo `impliedVolatility` |
| `underlying_price` | single underlying reference value copied to every row |

Normalization rules:

- uppercase `ticker`
- lowercase `type`
- parse `expiration` with fail-fast validation
- coerce numeric fields with invalid values becoming `NaN`
- compute `mid` from normalized `bid` and `ask`
- emit only the canonical column order already enforced by the offline loader

Recommended output column order:

1. `ticker`
2. `expiration`
3. `strike`
4. `type`
5. `bid`
6. `ask`
7. `mid`
8. `implied_vol`
9. `underlying_price`

## Alias Mapping

The scanner loader already supports safe aliases for local inputs, but this Yahoo ingestion command should write canonical columns directly rather than relying on alias fallback.

Canonical direct writes should use:

- `expiration`, not `expiry`
- `strike`, not `strike_price`
- `type`, not `option_type`
- `implied_vol`, not `iv` or `implied_volatility`

Reason:

- the ingestion utility is the contract boundary, so it should produce the exact scanner input shape
- alias normalization should remain a safety net for externally supplied local files, not the primary output format of first-party ingestion

## Validation Steps

The command should validate in this order:

1. CLI argument validation
   - `ticker` is non-empty after trimming
   - `expiration` parses as `YYYY-MM-DD`
   - output path resolution is deterministic
   - existing output file is rejected unless `--overwrite` is present

2. Dependency validation
   - `yfinance` import succeeds only when this command is invoked

3. Vendor availability validation
   - ticker exposes option expirations
   - requested expiration exists in the returned Yahoo expiration set

4. Underlying price validation
   - retrieve one numeric underlying reference price
   - fail if no numeric underlying reference can be established

5. Chain payload validation
   - calls frame and puts frame may each be empty, but not both empty
   - required vendor fields exist: `strike`, `bid`, `ask`, `impliedVolatility`

6. Normalized contract validation
   - normalize calls and puts into canonical rows
   - pass the resulting dataframe through `validate_option_quote_frame(...)`
   - reject if required canonical columns are missing after normalization

7. Artifact write validation
   - create parent directories as needed
   - write normalized CSV
   - optionally write metadata sidecar

Recommended additional data-quality checks:

- reject rows with missing `strike`
- warn or count rows where `bid` or `ask` is missing and becomes `NaN`
- record counts of rows with suspicious quote values such as negative `bid`, negative `ask`, or negative `implied_vol` rather than silently mutating them at ingestion
- sort output deterministically by `expiration`, `type`, then `strike`

## Metadata And Provenance

Because the scanner input contract should stay narrow, provenance should be captured in a sidecar metadata file rather than expanding the scanner CSV.
The strict historical snapshot path expects that sidecar to carry its own `snapshot_id`.

Recommended sidecar path:

`{normalized_csv_path}.meta.json`

Recommended metadata fields:

- `snapshot_id`
- `snapshot_source`
- `source_vendor`
  - `yahoo_finance`
- `source_library`
  - `yfinance`
- `source_library_version`
- `ticker_requested`
- `ticker_normalized`
- `expiration_requested`
- `expiration_resolved`
- `expiration_start`
- `expiration_end`
- `fetched_at_utc`
- `quote_observed_at`
- `underlying_price`
- `underlying_price_observed_at`
- `underlying_price_source`
  - for example `history.close`
- `calls_row_count`
- `puts_row_count`
- `normalized_row_count`
- `output_csv_path`
- `raw_cache_path`
- `raw_payload_written`
- `cache_hit`
- `cache_ttl_seconds`
- `command_version`
  - repo-local command schema version, for example `1`

Optional raw-field audit content in metadata:

- list of raw column names observed in calls
- list of raw column names observed in puts
- per-column null counts for canonical output

Why sidecar metadata instead of extra CSV columns:

- preserves exact compatibility with the current offline scanner contract
- avoids teaching the scanner to ignore ingestion-only fields
- keeps provenance available for debugging and reproducibility

## Caching Behavior

Caching should apply to the vendor fetch step, not to the scanner.

Recommended behavior:

- normalized CSV output is always a local artifact and may be reused indefinitely by offline scanner runs
- raw Yahoo fetch metadata may be cached under `outputs/yahoo_option_chains/cache/`
- if `--use-cache` is set and a cache entry is still fresh under `--cache-ttl-seconds`, the command may rebuild the normalized CSV from cached raw data instead of refetching
- if cache is stale or absent, the command fetches live data and refreshes cache artifacts

Recommended cache key:

- normalized uppercase ticker
- requested expiration date
- ingestion schema version

Recommended stale-cache behavior:

- default to refetch
- if refetch fails and a stale cache exists, do not silently fall back unless a future explicit flag such as `--allow-stale-cache` is reviewed and approved

Reason:

- silent stale fallback can blur provenance and date expectations
- explicit cache policy keeps offline research artifacts easier to audit

## Failure Modes

Expected failures and recommended behavior:

- missing optional dependency
  - fail with actionable install guidance
- invalid ticker argument
  - fail fast before network access
- invalid expiration format
  - fail fast before network access
- expiration not listed for ticker
  - fail with the available expiration set or a concise summary of it
- Yahoo returns no option expirations
  - fail with vendor-unavailable message
- calls and puts both empty
  - fail with no-data message
- missing numeric underlying price
  - fail because `underlying_price` is required by the scanner contract
- vendor schema drift
  - fail if required Yahoo fields are absent
- timeout, DNS, SSL, or other network errors
  - fail without writing partial normalized CSV output
- output path already exists without `--overwrite`
  - fail before writing
- cache read corruption
  - ignore corrupted cache and attempt fresh fetch, then fail if fresh fetch also fails

Failure output should be concise, explicit, and non-promotional. It should not suggest trades, strategies, or next-step recommendations beyond artifact-generation troubleshooting.

## Rate-Limit And Network Caveats

This utility will depend on an unofficial client library over a third-party consumer data source, so the design should document the operational caveats clearly:

- Yahoo Finance availability is not guaranteed
- `yfinance` is not an exchange-grade market-data interface
- responses may be delayed, incomplete, throttled, or schema-shifted
- repeated requests across many tickers or expirations may trigger throttling
- the command is suitable only for research snapshot generation, not live or latency-sensitive workflows
- network access is required for a live fetch, but not for scanner consumption of previously written local CSV files

Recommended help-text sentence:

`This command fetches a best-effort Yahoo Finance snapshot for local research artifacts only. The scanner itself remains offline and consumes local files only.`

## Test Strategy

Tests for the ingestion command must be fully offline and rely on mocked `yfinance` responses only.

Recommended test layers:

1. Unit tests for CLI argument validation
   - missing required args
   - invalid date
   - output overwrite guard

2. Unit tests for normalization
   - mocked calls and puts dataframes normalize into exact canonical column order
   - `mid` is computed correctly
   - ticker uppercasing and type lowercasing are enforced

3. Unit tests for metadata/provenance
   - metadata file includes required provenance keys
   - cache-hit and cache-miss states are represented correctly

4. Unit tests for vendor failure handling
   - no expirations
   - requested expiration absent
   - empty calls and puts
   - missing underlying price
   - missing required vendor columns
   - timeout/network exception propagation

5. Contract tests
   - generated CSV round-trips through `load_option_quotes(...)`
   - generated CSV can feed `build_scanner_opportunities(...)` when mocked data is internally coherent

Mocking approach:

- mock `yfinance.Ticker`
- mock `Ticker.options`
- mock `Ticker.option_chain(expiration)`
- mock underlying-price retrieval method
- do not hit the network under any test path

Explicit offline boundary for tests:

- scanner tests remain offline and fixture-backed
- existing scanner tests must not import, invoke, or depend on Yahoo ingestion
- new Yahoo ingestion tests must use mocked `yfinance` objects only
- CI should remain green in environments with no outbound network access

## Interaction With Existing Code

This design implies a separation that the current repo should preserve during any future implementation:

- scanner runtime logic stays unchanged
- offline scan commands stay unchanged
- Yahoo ingestion is a separate artifact-generation command
- the canonical scanner input remains the existing `OptionQuoteRow` CSV contract

Implementation should avoid making the current offline path import `yfinance` at module import time. If that import remains unconditional in shared code, offline-only users may inherit an unnecessary dependency burden.

## Proposed User Workflow

The intended workflow is two-step:

1. Run Yahoo ingestion once to generate a local contract-compliant CSV snapshot.
2. Run the existing offline scanner against that local CSV file.

Example:

```powershell
python -m options_edge_scanner.cli.yahoo_option_chain_ingest `
  --ticker AAPL `
  --expiration 2026-09-18 `
  --output outputs/yahoo_option_chains/AAPL/AAPL_2026-09-18_yahoo.csv

python -m options_edge_scanner.cli.offline_scan `
  --input outputs/yahoo_option_chains/AAPL/AAPL_2026-09-18_yahoo.csv `
  --output outputs/offline_scan_aapl_2026-09-18.csv `
  --as-of 2026-06-12
```

This preserves the current scanner boundary: the scanner consumes only local files.

## Review Checklist

Before implementation, confirm:

- command name is acceptable
- optional dependency packaging approach is acceptable
- output and cache folder conventions are acceptable
- metadata sidecar shape is acceptable
- fail-fast rules are acceptable
- mocked-test-only strategy is acceptable
- scanner/offline test boundary remains explicit and unchanged

## Explicit Boundary Statement

The scanner test suite must remain offline and fixture-backed.

No scanner runtime logic should fetch Yahoo data.
No scanner test should require network access.
Any future Yahoo ingestion tests must mock `yfinance` responses rather than calling the network.
