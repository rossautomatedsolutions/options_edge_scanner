"""Research-only offline scan entrypoint for local option quote files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.data.provenance import enrich_option_quote_provenance
from options_edge_scanner.scanner.engine import build_scanner_artifacts
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings
from options_edge_scanner.scanner.reporting import build_scan_report, write_scan_report


def run_offline_scan(
    *,
    input_path: str | Path,
    output_path: str | Path,
    report_output_path: str | Path | None = None,
    as_of: str | None = None,
    spot: float | None = None,
    spot_observed_at: str | None = None,
    spot_source: str | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
    allow_unsafe_as_of: bool = False,
) -> Path:
    """Run the deterministic offline scanner from a local quote file."""
    input_file = Path(input_path)
    output_file = Path(output_path)

    option_quotes = load_option_quotes(input_file, require_underlying_price=spot is None)
    option_quotes = enrich_option_quote_provenance(option_quotes, input_path=input_file)
    if spot is not None:
        option_quotes["underlying_price"] = float(spot)
        option_quotes["underlying_price_source"] = (
            str(spot_source).strip() if spot_source is not None and str(spot_source).strip() else "user.override"
        )
        if spot_observed_at is None:
            option_quotes["underlying_price_observed_at"] = pd.NaT
            if not allow_unsafe_as_of:
                raise ValueError(
                    "Using --spot requires --spot-observed-at for safe provenance, "
                    "or pass --allow-unsafe-as-of to proceed without it."
                )
        else:
            parsed_spot_observed_at = pd.to_datetime(spot_observed_at, errors="coerce", utc=True)
            if pd.isna(parsed_spot_observed_at):
                raise ValueError("spot_observed_at must be a valid timestamp.")
            option_quotes["underlying_price_observed_at"] = pd.Timestamp(
                parsed_spot_observed_at
            ).tz_localize(None)

    underlying_prices = pd.to_numeric(option_quotes.get("underlying_price"), errors="coerce")
    if underlying_prices is None or not underlying_prices.gt(0).any():
        raise ValueError(
            "Offline scan requires underlying_price in the input file or an explicit --spot value."
        )

    settings = quality_settings or OfflineScanQualitySettings()
    artifacts = build_scanner_artifacts(
        option_quotes,
        as_of=as_of,
        quality_settings=settings,
        allow_unsafe_as_of=allow_unsafe_as_of,
    )
    opportunities = artifacts.opportunities

    output_file.parent.mkdir(parents=True, exist_ok=True)
    opportunities.to_csv(output_file, index=False)
    if report_output_path is not None:
        report = build_scan_report(
            artifacts,
            input_path=input_file,
            output_path=output_file,
            settings=settings,
        )
        write_scan_report(report, report_output_path)
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
        "--report-output",
        dest="report_output",
        default=None,
        help="Optional JSON path for a machine-readable scan report artifact",
    )
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
        "--spot-observed-at",
        default=None,
        help="Observation timestamp for a user-supplied --spot value, such as 2026-01-02T15:30:00Z",
    )
    parser.add_argument(
        "--spot-source",
        default=None,
        help="Optional provenance label for a user-supplied --spot value; defaults to user.override",
    )
    parser.add_argument(
        "--allow-unsafe-as-of",
        action="store_true",
        help="Allow scans that lack observation provenance or that use an as_of date before the observed snapshot",
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
    parser.add_argument(
        "--max-spread-market-width-pct",
        type=float,
        default=0.8,
        help="Maximum net spread bid/ask width divided by quoted midpoint debit; default 0.8",
    )
    parser.add_argument(
        "--min-liquidity-score",
        type=float,
        default=None,
        help="Optional minimum 0..1 execution-liquidity score after spread construction",
    )
    parser.add_argument(
        "--execution-slippage-floor",
        type=float,
        default=0.2,
        help="Minimum fraction of the spread market width added above midpoint; default 0.2",
    )
    parser.add_argument(
        "--execution-slippage-cap",
        type=float,
        default=0.5,
        help="Maximum fraction of the spread market width added above midpoint; default 0.5",
    )
    parser.add_argument(
        "--min-expected-value",
        type=float,
        default=0.0,
        help="Minimum execution-adjusted expected value required for ranked output; default 0.0",
    )
    parser.add_argument(
        "--min-probability-of-profit",
        type=float,
        default=0.3,
        help="Minimum probability of profit required for ranked output; default 0.3",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Maximum number of ranked opportunities to return; default 20",
    )
    parser.add_argument(
        "--max-per-ticker",
        type=int,
        default=None,
        help="Optional concentration cap on ranked opportunities per ticker",
    )
    parser.add_argument(
        "--max-per-expiration",
        type=int,
        default=None,
        help="Optional concentration cap on ranked opportunities per expiration date",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the offline scan."""
    args = build_parser().parse_args(argv)
    output_file = run_offline_scan(
        input_path=args.input,
        output_path=args.output,
        report_output_path=args.report_output,
        as_of=args.as_of,
        spot=args.spot,
        spot_observed_at=args.spot_observed_at,
        spot_source=args.spot_source,
        allow_unsafe_as_of=args.allow_unsafe_as_of,
        quality_settings=OfflineScanQualitySettings(
            max_abs_moneyness_pct=args.max_abs_moneyness_pct,
            max_debit_fraction_of_width=args.max_debit_fraction,
            max_bid_ask_spread_pct=args.max_bid_ask_spread_pct,
            min_volume=args.min_volume,
            min_open_interest=args.min_open_interest,
            min_abs_delta=args.min_abs_delta,
            max_abs_delta=args.max_abs_delta,
            max_spread_market_width_pct=args.max_spread_market_width_pct,
            min_liquidity_score=args.min_liquidity_score,
            execution_slippage_floor=args.execution_slippage_floor,
            execution_slippage_cap=args.execution_slippage_cap,
            min_expected_value=args.min_expected_value,
            min_probability_of_profit=args.min_probability_of_profit,
            top_n=args.top_n,
            max_positions_per_ticker=args.max_per_ticker,
            max_positions_per_expiration=args.max_per_expiration,
        ),
    )
    print(
        "Offline research-only scan complete. "
        f"No live data was fetched. Output written to: {output_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
