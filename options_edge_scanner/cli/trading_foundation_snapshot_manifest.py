"""CLI for building strict snapshot manifests from Trading Foundation daily snapshot files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from options_edge_scanner.data.trading_foundation import (
    write_trading_foundation_snapshot_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for Trading Foundation snapshot manifest generation."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a strict historical snapshot manifest plus metadata sidecars that point at "
            "canonical Trading Foundation option_snapshot files without copying the raw chains."
        )
    )
    parser.add_argument(
        "--historical-data-root",
        required=True,
        help="Canonical Trading Foundation historical_data root, e.g. C:\\Users\\RAS\\...\\historical_data",
    )
    parser.add_argument("--ticker", required=True, help="Underlying ticker symbol, e.g. SPY")
    parser.add_argument(
        "--snapshot-date",
        dest="snapshot_dates",
        action="append",
        default=None,
        help="Explicit snapshot date in YYYY-MM-DD format; repeat for multiple dates",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Optional inclusive snapshot-date lower bound when selecting from the folder inventory",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Optional inclusive snapshot-date upper bound when selecting from the folder inventory",
    )
    parser.add_argument(
        "--manifest-output",
        required=True,
        help="Strict HistoricalSnapshotManifestRow CSV output path",
    )
    parser.add_argument(
        "--metadata-dir",
        default=None,
        help="Optional metadata sidecar directory; defaults to <manifest stem>_metadata beside the manifest",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, build the manifest bundle, and print one concise summary."""
    args = build_parser().parse_args(argv)
    artifacts = write_trading_foundation_snapshot_manifest(
        args.historical_data_root,
        ticker=args.ticker,
        manifest_output_path=args.manifest_output,
        snapshot_dates=args.snapshot_dates,
        start_date=args.start_date,
        end_date=args.end_date,
        metadata_dir=args.metadata_dir,
    )
    print(
        "Trading Foundation snapshot manifest complete. "
        f"manifest={artifacts.manifest_path}, "
        f"snapshots={len(artifacts.snapshot_dates)}, "
        f"metadata_dir={Path(artifacts.metadata_paths[0]).parent if artifacts.metadata_paths else ''}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
