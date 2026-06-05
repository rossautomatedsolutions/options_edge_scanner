"""Research-only offline scan entrypoint for local option quote files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities


def run_offline_scan(
    *,
    input_path: str | Path,
    output_path: str | Path,
    as_of: str | None = None,
) -> Path:
    """Run the deterministic offline scanner from a local quote file."""
    input_file = Path(input_path)
    output_file = Path(output_path)

    option_quotes = load_option_quotes(input_file)
    opportunities = build_scanner_opportunities(option_quotes, as_of=as_of)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    opportunities.to_csv(output_file, index=False)
    return output_file


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the offline scan entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only deterministic scanner from a local option-quote "
            "CSV or parquet file and write ranked opportunities to CSV."
        )
    )
    parser.add_argument("--input", required=True, help="Local input option-quote CSV/parquet path")
    parser.add_argument("--output", required=True, help="Output CSV path for ranked opportunities")
    parser.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        help="Optional deterministic as-of date (YYYY-MM-DD) for DTE calculations",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the offline scan."""
    args = build_parser().parse_args(argv)
    output_file = run_offline_scan(
        input_path=args.input,
        output_path=args.output,
        as_of=args.as_of,
    )
    print(
        "Offline research-only scan complete. "
        f"No live data was fetched. Output written to: {output_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
