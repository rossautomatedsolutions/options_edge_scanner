"""CLI for materializing realized outcome artifacts from strict snapshots."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from options_edge_scanner.calibration.materialization import (
    materialize_realized_outcomes_from_snapshot_manifest,
    write_realized_outcomes,
)


def run_realized_outcome_materialization(
    *,
    manifest_path: str | Path,
    realized_underlying_paths: list[str | Path],
    output_path: str | Path,
) -> tuple[int, int]:
    """Materialize realized outcomes and persist one CSV artifact."""
    artifacts = materialize_realized_outcomes_from_snapshot_manifest(
        manifest_path=manifest_path,
        realized_underlying_paths=realized_underlying_paths,
    )
    write_realized_outcomes(artifacts.outcomes, output_path)
    return len(artifacts.required_observations), len(artifacts.outcomes)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for realized outcome materialization."""
    parser = argparse.ArgumentParser(
        description=(
            "Read a strict historical option-snapshot manifest plus one or more normalized "
            "realized-underlying artifacts, then emit contract-valid RealizedOutcomeRow CSVs."
        )
    )
    parser.add_argument("--manifest", required=True, help="Strict historical snapshot manifest CSV or JSON path")
    parser.add_argument(
        "--realized-underlying",
        dest="realized_underlying_paths",
        required=True,
        action="append",
        help="Normalized realized underlying CSV path; repeat for multiple artifacts",
    )
    parser.add_argument("--output", required=True, help="RealizedOutcomeRow CSV output path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, materialize realized outcomes, and print one concise summary."""
    args = build_parser().parse_args(argv)
    required_count, output_count = run_realized_outcome_materialization(
        manifest_path=args.manifest,
        realized_underlying_paths=args.realized_underlying_paths,
        output_path=args.output,
    )
    print(
        "Realized outcome materialization complete. "
        f"required_outcome_groups={required_count}, "
        f"materialized_outcomes={output_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
