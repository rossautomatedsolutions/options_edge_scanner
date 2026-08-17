"""Research-only offline batch scan entrypoint for local quote manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from options_edge_scanner.cli.offline_scan import run_offline_scan
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


MANIFEST_REQUIRED_COLUMNS = ("input_path", "output_path", "as_of")
SUMMARY_OUTPUT_COLUMNS = ("input_path", "output_path", "as_of", "status", "row_count", "error_message")


def _resolve_manifest_path(path_ref: str, *, manifest_dir: Path) -> Path:
    """Resolve one manifest path relative to the manifest location."""
    path = Path(path_ref)
    if path.is_absolute():
        return path
    return (manifest_dir / path).resolve(strict=False)


def _load_manifest(manifest_path: str | Path) -> pd.DataFrame:
    """Load a batch manifest from local CSV or JSON."""
    path = Path(manifest_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        manifest = pd.read_csv(path)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        manifest = pd.DataFrame(payload)
    else:
        raise ValueError(f"Unsupported manifest file type: {path.suffix or '<no extension>'}")

    missing_columns = [column for column in MANIFEST_REQUIRED_COLUMNS if column not in manifest.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required manifest columns: {missing}")

    return manifest.loc[:, list(MANIFEST_REQUIRED_COLUMNS)].reset_index(drop=True)


def _validate_manifest_row(row: pd.Series, row_number: int, *, manifest_dir: Path) -> dict[str, str]:
    """Validate one manifest row and return normalized string paths/date."""
    input_path = str(row["input_path"]).strip()
    output_path = str(row["output_path"]).strip()
    as_of = str(row["as_of"]).strip()

    if not input_path:
        raise ValueError(f"Manifest row {row_number} has an empty input_path")
    if not output_path:
        raise ValueError(f"Manifest row {row_number} has an empty output_path")
    if not as_of:
        raise ValueError(f"Manifest row {row_number} has an empty as_of")

    parsed_as_of = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(parsed_as_of):
        raise ValueError(f"Manifest row {row_number} has invalid as_of date: {as_of}")

    input_file = _resolve_manifest_path(input_path, manifest_dir=manifest_dir)
    if not input_file.exists():
        raise FileNotFoundError(
            f"Manifest row {row_number} input file does not exist: {input_file}"
        )
    output_file = _resolve_manifest_path(output_path, manifest_dir=manifest_dir)

    return {
        "input_path": str(input_file),
        "output_path": str(output_file),
        "as_of": parsed_as_of.strftime("%Y-%m-%d"),
    }


def _write_summary(summary: pd.DataFrame, summary_output_path: str | Path | None) -> None:
    """Write the batch summary CSV if a destination is provided."""
    if summary_output_path is None:
        return

    output_file = Path(summary_output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_file, index=False)


def run_offline_batch_scan(
    manifest_path: str | Path,
    *,
    summary_output_path: str | Path | None = None,
    continue_on_error: bool = False,
    allow_unsafe_as_of: bool = False,
    quality_settings: OfflineScanQualitySettings | None = None,
) -> pd.DataFrame:
    """Run the deterministic offline scanner for each manifest row."""
    manifest = _load_manifest(manifest_path)
    manifest_dir = Path(manifest_path).resolve(strict=False).parent
    summary_rows: list[dict[str, Any]] = []

    for idx, row in manifest.iterrows():
        row_number = idx + 1
        raw_input_path = str(row.get("input_path", "")).strip()
        raw_output_path = str(row.get("output_path", "")).strip()
        raw_as_of = str(row.get("as_of", "")).strip()

        try:
            validated = _validate_manifest_row(
                row,
                row_number=row_number,
                manifest_dir=manifest_dir,
            )
            output_file = run_offline_scan(
                input_path=validated["input_path"],
                output_path=validated["output_path"],
                as_of=validated["as_of"],
                allow_unsafe_as_of=allow_unsafe_as_of,
                quality_settings=quality_settings,
            )
            output_frame = pd.read_csv(output_file)
            summary_rows.append(
                {
                    "input_path": validated["input_path"],
                    "output_path": str(output_file),
                    "as_of": validated["as_of"],
                    "status": "success",
                    "row_count": int(len(output_frame)),
                    "error_message": "",
                }
            )
        except Exception as exc:
            summary_rows.append(
                {
                    "input_path": raw_input_path,
                    "output_path": raw_output_path,
                    "as_of": raw_as_of,
                    "status": "failed",
                    "row_count": 0,
                    "error_message": str(exc),
                }
            )
            if not continue_on_error:
                summary = pd.DataFrame(summary_rows, columns=list(SUMMARY_OUTPUT_COLUMNS))
                _write_summary(summary, summary_output_path)
                raise

    summary = pd.DataFrame(summary_rows, columns=list(SUMMARY_OUTPUT_COLUMNS))
    _write_summary(summary, summary_output_path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the offline batch scan entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only deterministic scanner for each local quote file "
            "listed in a CSV or JSON manifest and write ranked CSV outputs."
        )
    )
    parser.add_argument("--manifest", required=True, help="Local CSV or JSON batch manifest path")
    parser.add_argument(
        "--summary-output",
        dest="summary_output",
        default=None,
        help="Optional CSV path for a batch summary artifact",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing later manifest rows after a row-level failure",
    )
    parser.add_argument(
        "--allow-unsafe-as-of",
        action="store_true",
        help="Allow rows that lack observation provenance or that use as_of dates before the observed snapshot",
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
        "--max-spread-market-width-pct",
        type=float,
        default=0.8,
        help="Maximum net spread bid/ask width divided by quoted midpoint debit; default 0.8",
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
        help="Maximum number of ranked opportunities to return per manifest row; default 20",
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
    """Parse arguments and run the offline batch scan."""
    args = build_parser().parse_args(argv)
    summary = run_offline_batch_scan(
        args.manifest,
        summary_output_path=args.summary_output,
        continue_on_error=args.continue_on_error,
        allow_unsafe_as_of=args.allow_unsafe_as_of,
        quality_settings=OfflineScanQualitySettings(
            max_abs_moneyness_pct=args.max_abs_moneyness_pct,
            max_debit_fraction_of_width=args.max_debit_fraction,
            max_bid_ask_spread_pct=args.max_bid_ask_spread_pct,
            max_spread_market_width_pct=args.max_spread_market_width_pct,
            min_volume=args.min_volume,
            min_open_interest=args.min_open_interest,
            min_abs_delta=args.min_abs_delta,
            max_abs_delta=args.max_abs_delta,
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

    print("Offline research-only batch scan complete. No live data was fetched.")
    for row in summary.to_dict("records"):
        print(
            f"{row['input_path']} -> {row['output_path']} "
            f"(as_of={row['as_of']}, status={row['status']}, "
            f"row_count={row['row_count']}, error_message={row['error_message']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
