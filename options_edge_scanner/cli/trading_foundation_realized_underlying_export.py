"""CLI for exporting normalized realized underlying artifacts from Trading Foundation EOD data."""

from __future__ import annotations

import argparse
from typing import Sequence

from options_edge_scanner.data.trading_foundation import (
    write_trading_foundation_realized_underlying,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for Trading Foundation realized-underlying export."""
    parser = argparse.ArgumentParser(
        description=(
            "Normalize canonical Trading Foundation EOD bars into the repo's "
            "RealizedUnderlyingObservationRow contract."
        )
    )
    parser.add_argument(
        "--historical-data-root",
        required=True,
        help="Canonical Trading Foundation historical_data root, e.g. C:\\Users\\RAS\\...\\historical_data",
    )
    parser.add_argument("--ticker", required=True, help="Underlying ticker symbol, e.g. SPY")
    parser.add_argument(
        "--start",
        default=None,
        help="Inclusive event-date lower bound in YYYY-MM-DD format when exporting by date range",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Inclusive event-date upper bound in YYYY-MM-DD format when exporting by date range",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Optional strict historical snapshot manifest. When supplied, the export derives the "
            "already-realized required expiration dates from the manifest instead of taking a raw date range."
        ),
    )
    parser.add_argument(
        "--realized-as-of",
        default=None,
        help=(
            "Optional timestamp or date used to decide which manifest-required expirations are already realized. "
            "Defaults to the current runtime timestamp."
        ),
    )
    parser.add_argument("--output", required=True, help="Normalized realized underlying CSV output path")
    parser.add_argument(
        "--required-outcome-horizon",
        default="expiration",
        help="Outcome horizon label embedded in the normalized contract; default expiration",
    )
    parser.add_argument(
        "--adjustment-mode",
        default="unknown",
        help="Adjustment-mode provenance label embedded in the normalized contract; default unknown",
    )
    parser.add_argument(
        "--acquired-at",
        default=None,
        help="Optional explicit acquired-at timestamp for deterministic backfills",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, export the artifact, and print one concise summary."""
    args = build_parser().parse_args(argv)
    if args.manifest is None and (args.start is None or args.end is None):
        raise SystemExit("Provide either --manifest or both --start and --end.")

    observations = write_trading_foundation_realized_underlying(
        args.historical_data_root,
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        output_path=args.output,
        manifest_path=args.manifest,
        realized_as_of=args.realized_as_of,
        required_outcome_horizon=args.required_outcome_horizon,
        adjustment_mode=args.adjustment_mode,
        acquired_at=args.acquired_at,
    )
    range_summary = (
        f"manifest={args.manifest}, realized_as_of={args.realized_as_of or 'runtime_now'}"
        if args.manifest is not None
        else f"start={args.start}, end={args.end}"
    )
    print(
        "Trading Foundation realized underlying export complete. "
        f"rows={len(observations)}, "
        f"ticker={args.ticker.upper()}, "
        f"{range_summary}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
