"""CLI for exporting safe scanner opportunities into calibration predictions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from options_edge_scanner.calibration import export_scanner_probability_predictions


def run_probability_prediction_export(
    *,
    opportunities_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Load scanner opportunities, export calibration predictions, and write CSV."""
    input_file = Path(opportunities_path)
    output_file = Path(output_path)

    opportunities = pd.read_csv(input_file)
    predictions = export_scanner_probability_predictions(opportunities)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_file, index=False)
    return output_file


def build_parser() -> argparse.ArgumentParser:
    """Create the parser for the prediction-export entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Export safe offline scanner opportunities into validated calibration "
            "prediction CSV artifacts."
        )
    )
    parser.add_argument(
        "--opportunities",
        required=True,
        help="Input scanner opportunity CSV produced by the maintained offline scanner",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path for the exported probability predictions",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, export predictions, and print one concise summary."""
    args = build_parser().parse_args(argv)
    output_file = run_probability_prediction_export(
        opportunities_path=args.opportunities,
        output_path=args.output,
    )
    print(
        "Probability prediction export complete. "
        f"No live data was fetched. Output written to: {output_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
