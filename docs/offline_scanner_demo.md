# Options Edge Scanner Public-Demo Recording Guide

The canonical public-demo notebook is [01_offline_scanner_demo.ipynb](../notebooks/01_offline_scanner_demo.ipynb). It runs entirely offline against the committed synthetic `XYZ` fixture and calls the production `run_scan(...)` API. It is a research walkthrough, not financial advice, an alert, a recommendation, or a brokerage workflow.

## Setup and launch

Run these commands from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m notebook notebooks\01_offline_scanner_demo.ipynb
```

In the notebook menu, choose **Kernel → Restart Kernel and Run All Cells**. Every cell should finish without editing a path, accessing the network, or creating a persistent output artifact.

For a command-line pre-recording check, use:

```powershell
jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=30 notebooks\01_offline_scanner_demo.ipynb
```

## Suggested 2–3 minute narration

1. **0:00–0:20 — purpose and boundary.** Explain that this is an offline, research-only scanner for debit vertical spreads. The output is an inspectable ranking, never a trade instruction.
2. **0:20–0:45 — input universe.** Point out the eight-row, committed synthetic fixture. It includes bid/ask, IV, spot, and quote/spot provenance so the real safety checks can run. Call out that it is synthetic demonstration data, not a live market snapshot.
3. **0:45–1:20 — production pipeline.** Run the scanner cell. Describe the stage-count table: validation/provenance, quote filters, vertical-spread generation, execution and quality checks, DTE eligibility, and the final shortlist. Mention that the notebook calls `run_scan(...)` directly and does not recreate a scoring formula.
4. **1:20–2:05 — ranked output and top row.** Read the compact output columns: spread geometry, quoted versus execution-adjusted debit, model probability, execution-adjusted EV, liquidity, and rank. Explain that the top row earns rank 1 from the scanner's reported ranking score, while the higher adjusted debit exposes the execution assumption.
5. **2:05–2:30 — auditability and limits.** Show the audit table: the run date, model version, counts, warnings, and the explicit absence of realized outcomes. Close with: “The scanner turns a broad options universe into a structured, inspectable shortlist while preserving the evidence, execution assumptions, exclusions, and data limitations behind each ranking.”

## Limitations to state on camera

- The notebook data is a small synthetic test fixture. It demonstrates contracts and pipeline behavior, not market performance.
- `lognormal_breakeven` is the current baseline probability model; it is not an empirically calibrated alpha model.
- Execution adjustments and liquidity diagnostics are conservative heuristics, not historical fill simulation.
- No realized outcomes are included in this fixture. The repository tracks outcomes separately for evaluation, but its accessible historical coverage is insufficient to establish effectiveness. Missing outcomes are not silently counted as wins, losses, or zeros.
- The repository has no live data fetch, order placement, brokerage authentication, live trading, or full lifecycle options backtest in this demo path.

## Maintained scanner path

The notebook uses these production components without duplicating their logic:

- `options_edge_scanner.data.loader.load_option_quotes(...)`
- `options_edge_scanner.scanner.engine.run_scan(...)`
- `ScannerConfig` and the machine-readable scan-report contract

The run writes its production CSV and JSON report to a temporary local directory, then displays compact views of their actual contents. Use `python -m options_edge_scanner.cli.offline_scan` when a persistent local CSV/JSON artifact is needed outside the notebook.
