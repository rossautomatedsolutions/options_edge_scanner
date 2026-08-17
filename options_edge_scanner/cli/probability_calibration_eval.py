"""Offline CLI for evaluating probability predictions against realized outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from options_edge_scanner.calibration import (
    ensure_parent,
    evaluate_probability_predictions,
)


def _write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write one machine-readable CSV artifact."""
    output_path = ensure_parent(path)
    frame.to_csv(output_path, index=False)
    return output_path


def run_probability_calibration_evaluation(
    *,
    predictions_path: str | Path,
    outcomes_path: str | Path,
    summary_output_path: str | Path,
    bins_output_path: str | Path,
    observations_output_path: str | Path | None = None,
    bin_count: int = 10,
    clip_epsilon: float = 1e-6,
    allow_shared_outcome_keys: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Evaluate one prediction/outcome pair and persist machine-readable artifacts."""
    predictions = pd.read_csv(predictions_path)
    outcomes = pd.read_csv(outcomes_path)
    artifacts = evaluate_probability_predictions(
        predictions,
        outcomes,
        bin_count=bin_count,
        clip_epsilon=clip_epsilon,
        allow_shared_outcome_keys=allow_shared_outcome_keys,
    )

    _write_csv(artifacts.summary, summary_output_path)
    _write_csv(artifacts.reliability_bins, bins_output_path)
    if observations_output_path is not None:
        _write_csv(artifacts.observations, observations_output_path)

    return (
        artifacts.summary,
        artifacts.reliability_bins,
        artifacts.observations,
        artifacts.reliability_summary,
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for offline probability calibration evaluation."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate research-only probability predictions against separate realized "
            "outcome artifacts and emit machine-readable calibration summaries."
        )
    )
    parser.add_argument("--predictions", required=True, help="ProbabilityPredictionRow CSV path")
    parser.add_argument("--outcomes", required=True, help="RealizedOutcomeRow CSV path")
    parser.add_argument("--summary-output", required=True, help="Calibration summary CSV output path")
    parser.add_argument("--bins-output", required=True, help="Reliability-bin CSV output path")
    parser.add_argument(
        "--observations-output",
        default=None,
        help="Optional joined evaluation-observation CSV output path",
    )
    parser.add_argument(
        "--bin-count",
        type=int,
        default=10,
        help="Number of fixed-width reliability bins on [0, 1]; default 10",
    )
    parser.add_argument(
        "--clip-epsilon",
        type=float,
        default=1e-6,
        help="Safe probability clipping epsilon for log loss; default 1e-6",
    )
    parser.add_argument(
        "--allow-shared-outcome-keys",
        action="store_true",
        help=(
            "Allow multiple predictions to map to the same required_outcome_key. "
            "Use only when you intentionally want to evaluate correlated predictions."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, run the evaluation, and print one concise summary."""
    args = build_parser().parse_args(argv)
    _summary, _bins, _observations, reliability_summary = run_probability_calibration_evaluation(
        predictions_path=args.predictions,
        outcomes_path=args.outcomes,
        summary_output_path=args.summary_output,
        bins_output_path=args.bins_output,
        observations_output_path=args.observations_output,
        bin_count=args.bin_count,
        clip_epsilon=args.clip_epsilon,
        allow_shared_outcome_keys=args.allow_shared_outcome_keys,
    )
    print("Probability calibration evaluation complete.")
    print(reliability_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
