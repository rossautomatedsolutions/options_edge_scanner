# Options Edge Scanner Next Workstream Review

Historical note:
This document records an earlier June 2026 planning snapshot.
For the current repo-local status, use [offline_scanner_readiness_review.md](offline_scanner_readiness_review.md).

## Current Synced Commit Evidence

- Canonical local repo reviewed: `C:\GitHub\options_edge_scanner`
- Remote: `https://github.com/rossautomatedsolutions/options_edge_scanner.git`
- Review baseline from `git status -sb`: `## main...origin/main`
- Review baseline from `git log --oneline --decorate -5`: `d67bdfb (HEAD -> main, origin/main, origin/HEAD) Refine offline scanner hardening closeout`

This review is repo-local and reflects the committed state aligned on `main` at `d67bdfb`.

## Completed Tracks Supported By Repo Evidence

### Scanner strike alias support

- `options_edge_scanner/data/loader.py` implements safe input-column aliases including `strike_price -> strike`.
- The same loader also normalizes `option_type -> type`, `expiry` family aliases to `expiration`, and `iv` / `implied_volatility` to `implied_vol`.
- `docs/data_contracts.md` documents safe alias normalization as part of the offline adapter contract.
- `tests/test_offline_data_loader.py` now exercises a local alias fixture covering `expiry`, `strike_price`, `option_type`, and `iv`.
- `tests/fixtures/sample_option_chain_aliases.csv` provides the synthetic offline alias coverage fixture.

Status: implemented in the loader contract surface.

### Backtest contract fixtures

- `docs/backtest_contracts.md` defines `BacktestSignalRow`, `BacktestTradeResultRow`, `BacktestExitFixtureRow`, and `BacktestSummaryRow`.
- `tests/fixtures/` contains:
  - `sample_backtest_signals.csv`
  - `sample_backtest_trade_results.csv`
  - `sample_backtest_summary.csv`
  - `sample_backtest_exit_fixtures.csv`
- `tests/test_backtest_contract_fixtures.py` validates fixture columns, signal linkage, numeric/date parsing, and placeholder provenance text.
- `options_edge_scanner/backtest/runner.py` can load and validate exit fixtures, but still exposes a contract adapter rather than a real historical backtest engine.

Status: contract fixtures and validation coverage are present.

### Offline scanner CLI and fixture hardening

- `options_edge_scanner/cli/offline_scan.py` and `options_edge_scanner/cli/offline_batch_scan.py` provide offline-only CLI entrypoints.
- `tests/test_offline_scan_cli.py` covers help text, output writing, output schema, and deterministic ranked output ordering.
- `tests/test_offline_batch_scan_cli.py` covers batch output writing, optional summary output, missing manifest columns, `--continue-on-error`, and help text.
- `tests/test_offline_batch_scan_cli.py` now also covers manifest-path behavior: paths work exactly as provided when the current working directory resolves them, and they are not implicitly resolved relative to the manifest file location.
- `tests/test_offline_data_loader.py` covers canonical fixture loading, safe alias normalization through a synthetic local fixture, and missing required-column failure behavior.
- `tests/test_scanner_pipeline_integration.py` covers deterministic pipeline output shape, ranking order, and expected fixture values.
- `docs/offline_scanner_readiness_review.md` and `docs/offline_scanner_hardening_closeout.md` document the offline scanner hardening track as a research-only surface.

Status: the offline scanner path has meaningful fixture-driven regression coverage.

## Current Test Posture

- Scanner core model tests exist for probability estimation and spread EV calculation.
- Offline scanner coverage includes loader validation, single-run CLI behavior, batch CLI behavior, manifest failure handling, and deterministic integration behavior.
- Backtest coverage currently validates placeholder contract shapes, fixture integrity, exit-fixture loading, and deterministic zero-PnL placeholder behavior.
- Current fixture inventory is small and stable:
  - one canonical option-chain fixture
  - one batch manifest fixture
  - four backtest contract fixtures

Overall posture: strong for a small offline contract surface, but still narrow in fixture breadth.

## Open Limitations And Unknowns

- Alias support is implemented in `options_edge_scanner/data/loader.py`, and the current repo now has direct fixture-backed test coverage for `expiry`, `strike_price`, `option_type`, and `iv`.
- Batch manifest paths are treated as provided local filesystem paths; repo docs note they are not normalized relative to the manifest file location.
- Deterministic historical runs still rely on explicitly passing `--as-of`; repo docs note that omitting it can fall back to a current-date path.
- `options_edge_scanner/backtest/runner.py` remains a contract adapter with placeholder trade results, placeholder exit reasons, and `realized_pnl=0.0`.
- The repo does not yet show a real historical pricing model, fill model, exit-rule engine, or production runtime.
- Fixture breadth appears intentionally limited; the repo does not yet demonstrate broader vendor-format coverage.

## Recommended Next Safest Workstream

Recommendation: additional offline validation, centered on fixture expansion for existing loader and batch-manifest contracts.

Why this is the safest next move:

- It stays entirely inside the current research-only, offline boundary.
- It strengthens behavior that is already implemented and documented rather than opening a new economic or execution model.
- The repo already calls out specific contract edges that remain lightly tested: alias handling, manifest-path semantics, and deterministic `--as-of` usage.
- It improves confidence before any future backtest runner design work consumes scanner outputs more heavily.

Recommended focus inside this workstream:

- add any further alias-specific loader fixtures beyond the currently covered `strike_price`, `option_type`, `expiry`, and `iv` set only if a real contract need appears
- add explicit tests or docs-backed assertions for any additional manifest-path edge cases beyond the current "exactly as provided" behavior
- add deterministic validation around omitted `--as-of` behavior so the boundary is clearer in tests and docs

## Ranked Candidate Next Tasks

1. Add offline validation tests for safe input aliases and manifest-path behavior.
   Safety/value: highest. This now has initial coverage in the repo and remains the safest place for incremental expansion if another contract edge is discovered.

2. Expand fixture coverage with a few additional small contract-compliant input files.
   Safety/value: high. This broadens confidence without changing scanner economics or introducing live dependencies.

3. Perform docs and contract cleanup across README and contract docs for deterministic offline usage notes.
   Safety/value: moderate-high. Useful for clarity, but less protective than direct regression tests.

4. Draft backtest runner design notes before implementation.
   Safety/value: moderate. Safe if kept design-only, but it is a step closer to a more complex area where current behavior is still intentionally placeholder-only.

## Do Not Start Yet

- no broker integration
- no live execution
- no live market data fetching
- no strategy promotion
- no recommendation language

## Recommendation On Work Type

The next work should be: additional offline validation, with fixture expansion as the main implementation technique.

Not recommended as the immediate next step:

- backtest runner design as the primary workstream, because the runner is still explicitly placeholder-only and the safer path is to further harden the scanner contracts it would depend on
- docs-only cleanup as the primary workstream, because the repo already has substantial documentation and the larger remaining value is in regression protection

If a secondary companion task is desired, docs/contract cleanup is the safest follow-on after the offline validation additions land.
