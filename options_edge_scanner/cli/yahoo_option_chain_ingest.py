"""CLI entrypoint for optional Yahoo Finance option-chain ingestion."""

from __future__ import annotations

import argparse
from typing import Sequence

from options_edge_scanner.yahoo_ingestion import build_cli_summary, ingest_yahoo_option_chain


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for Yahoo option-chain ingestion."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a best-effort Yahoo Finance option-chain snapshot for local research "
            "artifacts only. The scanner itself remains offline and consumes local files only."
        )
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol to fetch, such as SPY")
    parser.add_argument(
        "--expiration",
        required=True,
        help="Explicit expiration date in YYYY-MM-DD format, or 'nearest'",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional explicit CSV path for the normalized local option-chain artifact",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Optional directory for a deterministic normalized CSV filename",
    )
    parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        default=None,
        help="Optional directory for raw Yahoo payload cache files",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing normalized output CSV if it already exists",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use a fresh cached raw payload if one is available",
    )
    parser.add_argument(
        "--cache-ttl-seconds",
        type=int,
        default=3600,
        help="Freshness window for raw payload cache reuse",
    )
    parser.add_argument(
        "--write-raw-json",
        action="store_true",
        help="Write the raw Yahoo payload JSON sidecar for provenance and debugging",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the optional Yahoo ingestion command."""
    args = build_parser().parse_args(argv)
    result = ingest_yahoo_option_chain(
        ticker=args.ticker,
        requested_expiration=args.expiration,
        output_path=args.output,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        overwrite=args.overwrite,
        use_cache=args.use_cache,
        cache_ttl_seconds=args.cache_ttl_seconds,
        write_raw_json=args.write_raw_json,
    )
    print(build_cli_summary(result))
    print(f"Metadata sidecar written to: {result.metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
