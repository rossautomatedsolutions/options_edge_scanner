# Offline Scanner Demo

This runbook is a small demo checkpoint for the committed offline scanner workflow.

The workflow is:

- offline only
- research/demo only
- not financial advice
- not a live signal engine
- not a brokerage or order-routing workflow

`offline_scan` reads a local option-chain file, applies conservative guardrails, ranks debit-spread candidates, and writes a local CSV output without fetching live data.
When provenance is available in the input file or sidecar metadata, the scanner also carries that provenance into the ranked output and rejects `as_of` dates that predate the observed snapshot unless `--allow-unsafe-as-of` is passed.
For stricter multi-snapshot research, `historical_snapshot_scan` reads one explicit snapshot manifest and refuses any snapshot whose option-chain and spot provenance cannot prove they came from the same logical observation timestamp.

## What The Default Guardrails Do

The default offline scan applies conservative quality checks intended to keep demo output more realistic:

- filters out legs that are too far from spot using `--max-abs-moneyness-pct 0.25`
- filters out spreads where debit is too large relative to width using `--max-debit-fraction 0.67`
- filters out legs with very wide quotes using `--max-bid-ask-spread-pct 0.25`
- optionally applies `--min-volume`, `--min-open-interest`, `--min-abs-delta`, and `--max-abs-delta` when those columns exist in the local file

If the input file does not contain `underlying_price`, pass `--spot` explicitly so the run remains offline and deterministic.

## Demo Commands

Use the existing local Yahoo chain CSV:

```powershell
$env:PYTHONPATH='.'
$INPUT_CSV = 'outputs\yahoo_option_chains\SPY_2026-07-17_yahoo.csv'
$OUTPUT_CSV = 'outputs\offline_scan_smoke\SPY_2026-07-17_ranked.csv'
$AS_OF = '2026-06-13'
```

The safest pattern is:

- if the input file already carries `quote_observed_at`, use an `--as-of` date on or after that observed date
- if you pass an intraday timestamp such as `2026-06-13T10:00:00Z`, the scanner checks it against the full observed timestamp rather than only the calendar day
- if the input file came from the Yahoo ingestion utility and already has provenance, omitting `--as-of` will make the scanner default to the observed snapshot date instead of the current day
- if you override spot with `--spot`, also pass `--spot-observed-at` for safe provenance, or combine the override with `--allow-unsafe-as-of` for intentionally ad hoc runs
- use `--allow-unsafe-as-of` only for intentionally ad hoc runs against legacy files

Confirm the input file exists:

```powershell
Get-ChildItem $INPUT_CSV
```

Run the offline scanner:

```powershell
python -m options_edge_scanner.cli.offline_scan `
  --input $INPUT_CSV `
  --output $OUTPUT_CSV `
  --as-of $AS_OF
```

Run the strict historical manifest scanner:

```powershell
python -m options_edge_scanner.cli.historical_snapshot_scan `
  --manifest path\to\strict_historical_manifest.csv `
  --output outputs\historical_snapshots\ranked_candidates.csv `
  --summary-output outputs\historical_snapshots\scan_summary.csv
```

Run the offline scanner when the file lacks `underlying_price`:

```powershell
python -m options_edge_scanner.cli.offline_scan `
  --input $INPUT_CSV `
  --output $OUTPUT_CSV `
  --as-of $AS_OF `
  --spot 741.75
```

Preview the first 10 ranked rows:

```powershell
Import-Csv $OUTPUT_CSV | Select-Object -First 10
```

Preview the provenance fields explicitly:

```powershell
Import-Csv $OUTPUT_CSV | Select-Object -First 5 as_of, quote_observed_at, underlying_price_observed_at, underlying_price_source
```

Group the ranked output by `option_type` and `spread_type`:

```powershell
Import-Csv $OUTPUT_CSV |
  Group-Object option_type, spread_type |
  Select-Object Count, Name
```

Check git status after the run:

```powershell
git status --short
```

## Output Expectations

The ranked CSV is a research/demo artifact. It is useful for inspecting:

- which spread types survived the default guardrails
- whether the snapshot is dominated by calls or puts
- whether a particular spot snapshot produces lopsided rankings even when both sides survive filtering

The output should be reviewed as offline ranking output only, not as a recommendation, alert, or executable signal.
Even the strict historical manifest path is still a snapshot-collection research tool, not a full historical backtest engine.
