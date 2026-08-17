"""Research-only CLI for strict multi-snapshot historical option scans."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from options_edge_scanner.data.historical_snapshot_loader import (
    HistoricalSnapshotSpec,
    collect_duplicate_snapshot_spec_errors,
    load_historical_snapshot,
    load_historical_snapshot_manifest_frame,
    validate_historical_snapshot_manifest_row,
)
from options_edge_scanner.data.provenance import SNAPSHOT_ID_COLUMN
from options_edge_scanner.scanner.engine import SCANNER_OUTPUT_COLUMNS, build_scanner_opportunities
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


SUMMARY_OUTPUT_COLUMNS = (
    SNAPSHOT_ID_COLUMN,
    "ticker",
    "as_of",
    "chain_path",
    "metadata_path",
    "status",
    "row_count",
    "error_message",
)


def _empty_candidates() -> pd.DataFrame:
    """Return one empty combined candidate frame with the canonical output contract."""
    return pd.DataFrame(columns=SCANNER_OUTPUT_COLUMNS)


def _stringify(value: Any) -> str:
    """Return one trimmed manifest-like scalar, or an empty string."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _summary_row_from_raw(row: pd.Series) -> dict[str, Any]:
    """Build one summary row from the raw manifest payload."""
    return {
        SNAPSHOT_ID_COLUMN: _stringify(row.get(SNAPSHOT_ID_COLUMN)),
        "ticker": _stringify(row.get("ticker")).upper(),
        "as_of": _stringify(row.get("as_of")),
        "chain_path": _stringify(row.get("chain_path")),
        "metadata_path": _stringify(row.get("metadata_path")),
    }


def _summary_row_from_spec(spec: HistoricalSnapshotSpec) -> dict[str, Any]:
    """Build one summary row from one validated manifest spec."""
    return {
        SNAPSHOT_ID_COLUMN: spec.snapshot_id,
        "ticker": spec.ticker,
        "as_of": spec.as_of,
        "chain_path": spec.chain_path_ref,
        "metadata_path": spec.metadata_path_ref,
    }


def _write_frame(frame: pd.DataFrame, output_path: str | Path) -> Path:
    """Write one CSV artifact and ensure its parent exists."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def _sort_combined_candidates(candidate_frame: pd.DataFrame) -> pd.DataFrame:
    """Return one deterministically ordered combined candidate artifact."""
    if candidate_frame.empty:
        return _empty_candidates()

    sort_columns = [
        "quote_observed_at",
        SNAPSHOT_ID_COLUMN,
        "expected_value",
        "edge_pct",
        "ticker",
        "expiration",
        "spread_type",
        "lower_strike",
        "upper_strike",
    ]
    return candidate_frame.sort_values(
        by=sort_columns,
        ascending=[True, True, False, False, True, True, True, True, True],
        kind="stable",
    ).reset_index(drop=True)


def run_historical_snapshot_scan(
    manifest_path: str | Path,
    *,
    output_path: str | Path,
    summary_output_path: str | Path | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scan every snapshot in one strict manifest and preserve per-row failures."""
    try:
        manifest = load_historical_snapshot_manifest_frame(manifest_path)
    except Exception as exc:
        combined_frame = _empty_candidates()
        summary_frame = pd.DataFrame(
            [
                {
                    SNAPSHOT_ID_COLUMN: "",
                    "ticker": "",
                    "as_of": "",
                    "chain_path": "",
                    "metadata_path": "",
                    "status": "failed",
                    "row_count": 0,
                    "error_message": str(exc),
                }
            ],
            columns=list(SUMMARY_OUTPUT_COLUMNS),
        )
        _write_frame(combined_frame, output_path)
        if summary_output_path is not None:
            _write_frame(summary_frame, summary_output_path)
        return combined_frame, summary_frame

    manifest_dir = Path(manifest_path).resolve(strict=False).parent
    settings = quality_settings or OfflineScanQualitySettings()

    specs_by_row: dict[int, HistoricalSnapshotSpec] = {}
    validation_errors: dict[int, str] = {}
    for index, row in manifest.iterrows():
        row_number = index + 1
        try:
            specs_by_row[row_number] = validate_historical_snapshot_manifest_row(
                row,
                row_number=row_number,
                manifest_dir=manifest_dir,
            )
        except Exception as exc:
            validation_errors[row_number] = str(exc)

    duplicate_errors = collect_duplicate_snapshot_spec_errors(specs_by_row.values())

    combined_candidates: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []

    for index, row in manifest.iterrows():
        row_number = index + 1
        raw_summary = _summary_row_from_raw(row)
        if row_number in validation_errors:
            summary_rows.append(
                {
                    **raw_summary,
                    "status": "failed",
                    "row_count": 0,
                    "error_message": validation_errors[row_number],
                }
            )
            continue

        spec = specs_by_row[row_number]
        spec_summary = _summary_row_from_spec(spec)
        if row_number in duplicate_errors:
            summary_rows.append(
                {
                    **spec_summary,
                    "status": "failed",
                    "row_count": 0,
                    "error_message": duplicate_errors[row_number],
                }
            )
            continue

        try:
            snapshot = load_historical_snapshot(spec)
            candidates = build_scanner_opportunities(
                snapshot.option_quotes,
                as_of=snapshot.as_of,
                quality_settings=settings,
                allow_unsafe_as_of=False,
            )
            combined_candidates.append(candidates)
            summary_rows.append(
                {
                    **spec_summary,
                    "status": "success",
                    "row_count": int(len(candidates)),
                    "error_message": "",
                }
            )
        except Exception as exc:
            summary_rows.append(
                {
                    **spec_summary,
                    "status": "failed",
                    "row_count": 0,
                    "error_message": str(exc),
                }
            )

    combined_frame = (
        _sort_combined_candidates(pd.concat(combined_candidates, ignore_index=True))
        if combined_candidates
        else _empty_candidates()
    )
    summary_frame = pd.DataFrame(summary_rows, columns=list(SUMMARY_OUTPUT_COLUMNS))

    _write_frame(combined_frame, output_path)
    if summary_output_path is not None:
        _write_frame(summary_frame, summary_output_path)
    return combined_frame, summary_frame


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the strict historical snapshot scan entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only deterministic scanner across a strict local historical "
            "snapshot manifest and preserve row-level provenance failures."
        )
    )
    parser.add_argument("--manifest", required=True, help="Historical snapshot manifest CSV or JSON path")
    parser.add_argument("--output", required=True, help="Combined ranked candidate CSV path")
    parser.add_argument(
        "--summary-output",
        dest="summary_output",
        default=None,
        help="Optional per-snapshot summary CSV path",
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
        help="Maximum number of ranked opportunities to return per snapshot; default 20",
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
    """Parse arguments, run the historical scan, and print one deterministic summary."""
    args = build_parser().parse_args(argv)
    _, summary = run_historical_snapshot_scan(
        args.manifest,
        output_path=args.output,
        summary_output_path=args.summary_output,
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

    requested = int(len(summary))
    failed = int((summary["status"] == "failed").sum()) if not summary.empty else 0
    valid = requested - failed
    candidate_rows = int(pd.to_numeric(summary["row_count"], errors="coerce").fillna(0).sum())

    print(
        "Historical offline scan complete. "
        f"snapshots_requested={requested}, "
        f"snapshots_valid={valid}, "
        f"snapshots_failed={failed}, "
        f"candidate_rows={candidate_rows}"
    )
    for row in summary.to_dict("records"):
        print(
            f"{row[SNAPSHOT_ID_COLUMN]} "
            f"(ticker={row['ticker']}, as_of={row['as_of']}, status={row['status']}, "
            f"row_count={row['row_count']}, error_message={row['error_message']})"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
