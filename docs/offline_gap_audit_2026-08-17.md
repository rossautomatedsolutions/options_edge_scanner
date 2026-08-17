# Offline Gap Audit And Main-Machine Gate

Date: Monday, August 17, 2026

## Closeout Status

- sandbox engineering complete
- `148` tests passing
- offline scanner research MVP ready for main-machine validation
- fresh-data validation remains outstanding
- empirical calibration remains outstanding
- backtesting/live execution remain intentionally out of scope

## Independent Audit Outcome

An independent reviewer pass found no `BLOCKER` issues in the maintained offline scanner path.

The highest-priority offline-safe gaps at the start of this pass were:

- `HIGH` `mid` derivation in the loader still disagreed with the documented contract.
- `HIGH` execution realism was still a flat transaction-cost subtraction with no spread-market entry model.
- `HIGH` ranking and portfolio/signal controls were still a minimal top-20 sort.
- `HIGH` the config-driven `run_scan(config)` path was still stubbed.
- `HIGH` calibration export required a Python helper rather than a maintained CLI.
- `MEDIUM` reporting was too thin for a clean handoff.
- `MEDIUM` batch manifests were cwd-dependent rather than manifest-relative.

## What This Pass Closed

- `HIGH` The loader now derives `mid` from `bid` and `ask` when raw inputs omit it.
- `HIGH` The maintained scanner now preserves quoted midpoint economics, computes conservative execution-adjusted entry economics, and carries spread-level liquidity diagnostics.
- `HIGH` Ranking now uses execution-aware `ranking_score`, configurable EV/PoP thresholds, optional per-ticker/per-expiration caps, and explicit `selection_rank`.
- `HIGH` `ScannerConfig` and `run_scan(config)` now point at the maintained offline workflow instead of returning an empty frame.
- `HIGH` Calibration export now has a maintained CLI: `python -m options_edge_scanner.cli.export_probability_predictions`.
- `MEDIUM` `offline_scan` can now emit a machine-readable JSON report artifact with counts, model metadata, active assumptions, and top-ranked rows.
- `MEDIUM` Batch manifests now resolve `input_path` and `output_path` relative to the manifest file for more portable handoff.

## Remaining Gaps

- `MEDIUM` Probability-model selection is still not configurable end to end; the maintained path still uses the default lognormal breakeven model.
- `LOW` Placeholder modules remain exposed in `models/pricing.py`, `signals/generator.py`, and `utils/logger.py`.
- `DATA-DEPENDENT` The repo still lacks a maintained strict option-chain acquisition source with trusted point-in-time quote timestamps for main-machine calibration work.
- `DATA-DEPENDENT` The repo still lacks a meaningful realized prediction/outcome dataset large enough for empirical calibration conclusions.
- `DATA-DEPENDENT` The current execution model is still a conservative heuristic, not a true historical fill simulator or lifecycle backtester.

## Main-Machine Validation Gate

The next main-machine run should be considered valid only if all of the following are true:

1. The option-chain source proves a trusted quote timestamp per snapshot.
2. The scan runs without `--allow-unsafe-as-of`.
3. The scan emits both the ranked CSV and the JSON report artifact.
4. Prediction export succeeds through the maintained CLI with no schema errors.
5. Realized outcomes are materialized from the strict snapshot manifest plus normalized underlying observations.
6. Calibration evaluation runs on those exported predictions and realized outcomes with no leakage or contract failures.

## Suggested Main-Machine Sequence

```powershell
python -m options_edge_scanner.cli.offline_scan `
  --input path\to\strict_snapshot.csv `
  --output outputs\main_machine\scan.csv `
  --report-output outputs\main_machine\scan_report.json `
  --as-of 2026-08-17

python -m options_edge_scanner.cli.export_probability_predictions `
  --opportunities outputs\main_machine\scan.csv `
  --output outputs\main_machine\predictions.csv

python -m options_edge_scanner.cli.materialize_realized_outcomes `
  --manifest path\to\strict_snapshot_manifest.csv `
  --realized-underlying outputs\realized_underlying\*.csv `
  --output outputs\main_machine\realized_outcomes.csv

python -m options_edge_scanner.cli.probability_calibration_eval `
  --predictions outputs\main_machine\predictions.csv `
  --outcomes outputs\main_machine\realized_outcomes.csv `
  --summary-output outputs\main_machine\calibration_summary.csv `
  --bins-output outputs\main_machine\calibration_bins.csv `
  --observations-output outputs\main_machine\calibration_observations.csv
```

## Validation Status

- `pytest -q`: passed on Monday, August 17, 2026 with `148 passed`
- `python -m compileall options_edge_scanner run_scanner.py`: passed on Monday, August 17, 2026
