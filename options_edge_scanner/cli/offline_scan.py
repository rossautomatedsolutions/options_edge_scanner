"""Research-only offline scan entrypoint for local option quote files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


def run_offline_scan(
    *,
    input_path: str | Path,
    output_path: str | Path,
    as_of: str | None = None,
    spot: float | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
) -> Path:
    """Run the deterministic offline scanner from a local quote file."""
    input_file = Path(input_path)
    output_file = Path(output_path)

    option_quotes = load_option_quotes(input_file, require_underlying_price=spot is None)
    if spot is not None:
        option_quotes["underlying_price"] = float(spot)

    underlying_prices = pd.to_numeric(option_quotes.get("underlying_price"), errors="coerce")
    if underlying_prices is None or not underlying_prices.gt(0).any():
        raise ValueError(
            "Offline scan requires underlying_price in the input file or an explicit --spot value."
        )

    opportunities = build_scanner_opportunities(
        option_quotes,
        as_of=as_of,
        quality_settings=quality_settings,
    )

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
    parser.add_argument(
        "--spot",
        type=float,
        default=None,
        help="Optional underlying spot override used when input data omits or should replace underlying_price",
    )
    parser.add_argument(
        "--max-abs-moneyness-pct",
        type=float,
        default=0.25,
        help="Maximum absolute strike distance from spot as a decimal fraction; default 0.25",
    )
    parser.add_argument(
        "--max-debit-fraction",
        type=float,
        default=0.67,
        help="Maximum debit divided by spread width; default 0.67",
    )
    parser.add_argument(
        "--max-bid-ask-spread-pct",
        type=float,
        default=0.25,
        help="Maximum per-leg bid/ask spread divided by mid; default 0.25",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=None,
        help="Optional minimum per-leg volume filter when a volume column exists",
    )
    parser.add_argument(
        "--min-open-interest",
        type=float,
        default=None,
        help="Optional minimum per-leg open interest filter when an open_interest/oi column exists",
    )
    parser.add_argument(
        "--min-abs-delta",
        type=float,
        default=None,
        help="Optional minimum absolute delta filter when a delta column exists",
    )
    parser.add_argument(
        "--max-abs-delta",
        type=float,
        default=None,
        help="Optional maximum absolute delta filter when a delta column exists",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the offline scan."""
    args = build_parser().parse_args(argv)
    output_file = run_offline_scan(
        input_path=args.input,
        output_path=args.output,
        as_of=args.as_of,
        spot=args.spot,
        quality_settings=OfflineScanQualitySettings(
            max_abs_moneyness_pct=args.max_abs_moneyness_pct,
            max_debit_fraction_of_width=args.max_debit_fraction,
            max_bid_ask_spread_pct=args.max_bid_ask_spread_pct,
            min_volume=args.min_volume,
            min_open_interest=args.min_open_interest,
            min_abs_delta=args.min_abs_delta,
            max_abs_delta=args.max_abs_delta,
        ),
    )
    print(
        "Offline research-only scan complete. "
        f"No live data was fetched. Output written to: {output_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
