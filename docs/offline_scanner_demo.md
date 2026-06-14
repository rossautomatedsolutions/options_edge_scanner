# Offline Scanner Demo

This runbook is a small demo checkpoint for the committed offline scanner workflow.

The workflow is:

- offline only
- research/demo only
- not financial advice
- not a live signal engine
- not a brokerage or order-routing workflow

`offline_scan` reads a local option-chain file, applies conservative guardrails, ranks debit-spread candidates, and writes a local CSV output without fetching live data.

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
