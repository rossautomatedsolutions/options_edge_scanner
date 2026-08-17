"""CLI for acquiring normalized realized underlying artifacts from Alpaca."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from options_edge_scanner.calibration.contracts import ensure_parent
from options_edge_scanner.data.alpaca_historical import (
    AlpacaRealizedUnderlyingAcquisition,
    AlpacaStockBarsRequest,
    acquire_alpaca_realized_underlying,
)
from options_edge_scanner.data.realized_underlying import write_realized_underlying_frame


def _default_metadata_path(output_path: str | Path) -> Path:
    """Return the default metadata sidecar path for one output CSV."""
    output = Path(output_path)
    return output.with_suffix(output.suffix + ".meta.json")


def _default_raw_pages_path(output_path: str | Path) -> Path:
    """Return the default raw-pages sidecar path for one output CSV."""
    output = Path(output_path)
    return output.with_suffix(output.suffix + ".raw.json")


def _write_json(payload: object, path: str | Path) -> Path:
    """Write one JSON payload deterministically."""
    output_path = ensure_parent(path)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def run_alpaca_realized_underlying_acquisition(
    *,
    ticker: str,
    start: str,
    end: str,
    output_path: str | Path,
    metadata_output_path: str | Path | None = None,
    raw_output_path: str | Path | None = None,
    timeframe: str = "1Day",
    adjustment: str = "raw",
    feed: str = "sip",
    sort: str = "asc",
    limit: int = 1000,
    required_outcome_horizon: str = "expiration",
    write_raw_json: bool = False,
) -> AlpacaRealizedUnderlyingAcquisition:
    """Acquire one normalized realized underlying artifact and persist it locally."""
    acquisition = acquire_alpaca_realized_underlying(
        AlpacaStockBarsRequest(
            ticker=ticker,
            start=start,
            end=end,
            timeframe=timeframe,
            adjustment=adjustment,
            feed=feed,
            sort=sort,
            limit=limit,
            required_outcome_horizon=required_outcome_horizon,
        )
    )
    write_realized_underlying_frame(acquisition.observations, output_path)
    _write_json(
        acquisition.metadata,
        metadata_output_path or _default_metadata_path(output_path),
    )
    if write_raw_json:
        _write_json(acquisition.raw_pages, raw_output_path or _default_raw_pages_path(output_path))
    return acquisition


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for Alpaca realized underlying acquisition."""
    parser = argparse.ArgumentParser(
        description=(
            "Acquire historical stock bars from Alpaca, normalize them into the repo's "
            "provider-neutral realized underlying contract, and write a local CSV artifact."
        )
    )
    parser.add_argument("--ticker", required=True, help="Underlying ticker, e.g. SPY")
    parser.add_argument("--start", required=True, help="Inclusive start date, e.g. 2026-06-15")
    parser.add_argument("--end", required=True, help="Inclusive end date, e.g. 2026-07-17")
    parser.add_argument("--output", required=True, help="Realized underlying CSV output path")
    parser.add_argument(
        "--metadata-output",
        default=None,
        help="Optional metadata JSON output path; defaults to <output>.meta.json",
    )
    parser.add_argument(
        "--raw-output",
        default=None,
        help="Optional raw pages JSON output path; defaults to <output>.raw.json when --write-raw-json is set",
    )
    parser.add_argument(
        "--timeframe",
        default="1Day",
        help="Explicit Alpaca timeframe; default 1Day",
    )
    parser.add_argument(
        "--adjustment",
        default="raw",
        help="Explicit Alpaca adjustment mode; default raw",
    )
    parser.add_argument(
        "--feed",
        default="sip",
        help="Explicit Alpaca feed; default sip",
    )
    parser.add_argument(
        "--sort",
        default="asc",
        help="Explicit Alpaca sort order; default asc",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Explicit Alpaca page limit; default 1000",
    )
    parser.add_argument(
        "--required-outcome-horizon",
        default="expiration",
        help="Outcome horizon label embedded in the normalized contract; default expiration",
    )
    parser.add_argument(
        "--write-raw-json",
        action="store_true",
        help="Write the fetched raw Alpaca response pages to JSON for auditability",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, acquire the artifact, and print one concise summary."""
    args = build_parser().parse_args(argv)
    acquisition = run_alpaca_realized_underlying_acquisition(
        ticker=args.ticker,
        start=args.start,
        end=args.end,
        output_path=args.output,
        metadata_output_path=args.metadata_output,
        raw_output_path=args.raw_output,
        timeframe=args.timeframe,
        adjustment=args.adjustment,
        feed=args.feed,
        sort=args.sort,
        limit=args.limit,
        required_outcome_horizon=args.required_outcome_horizon,
        write_raw_json=args.write_raw_json,
    )
    print(
        "Alpaca realized underlying acquisition complete. "
        f"ticker={acquisition.metadata['ticker']}, "
        f"rows={acquisition.metadata['row_count']}, "
        f"pages={acquisition.metadata['page_count']}, "
        f"artifact_id={acquisition.metadata['artifact_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
