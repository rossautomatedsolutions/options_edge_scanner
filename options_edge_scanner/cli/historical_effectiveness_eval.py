"""Research CLI for historical scanner effectiveness against realized outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd

from options_edge_scanner.calibration import (
    materialize_realized_outcomes_from_snapshot_manifest,
    write_realized_outcomes,
)
from options_edge_scanner.cli.historical_snapshot_scan import run_historical_snapshot_scan
from options_edge_scanner.data.trading_foundation import (
    write_trading_foundation_realized_underlying,
    write_trading_foundation_snapshot_manifest,
)
from options_edge_scanner.effectiveness import evaluate_scanner_effectiveness
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


def _write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return output_path


def _write_text(text: str, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _build_quality_settings(args: argparse.Namespace) -> OfflineScanQualitySettings:
    return OfflineScanQualitySettings(
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
    )


def _resolve_manifest_path(
    *,
    historical_data_root: str | Path,
    ticker: str,
    output_dir: str | Path,
    manifest_path: str | Path | None,
    snapshot_dates: Sequence[str] | None,
    start_date: str | None,
    end_date: str | None,
) -> Path:
    if manifest_path is not None:
        if snapshot_dates or start_date or end_date:
            raise ValueError(
                "Provide either --manifest or snapshot selection arguments, but not both."
            )
        return Path(manifest_path).resolve(strict=False)

    if not snapshot_dates and start_date is None and end_date is None:
        raise ValueError(
            "Provide --manifest or at least one of --snapshot-date, --start-date, or --end-date."
        )

    manifest_output_path = Path(output_dir) / f"{str(ticker).strip().lower()}_manifest.csv"
    artifacts = write_trading_foundation_snapshot_manifest(
        historical_data_root,
        ticker=ticker,
        manifest_output_path=manifest_output_path,
        snapshot_dates=snapshot_dates,
        start_date=start_date,
        end_date=end_date,
    )
    return artifacts.manifest_path


def _prepend_run_context(
    report_markdown: str,
    *,
    manifest_path: Path,
    realized_as_of: str,
    historical_data_root: str | Path,
    ticker: str,
    scan_summary: pd.DataFrame,
    required_outcome_count: int,
    eligible_required_outcome_count: int,
    future_required_outcome_count: int,
) -> str:
    requested_snapshot_count = int(len(scan_summary))
    failed_snapshot_count = (
        int((scan_summary["status"] == "failed").sum()) if not scan_summary.empty else 0
    )
    successful_snapshot_count = requested_snapshot_count - failed_snapshot_count
    context_lines = [
        "# Historical Effectiveness Run",
        "",
        "## Inputs",
        f"- ticker: {str(ticker).strip().upper()}",
        f"- historical data root: {Path(historical_data_root).resolve(strict=False)}",
        f"- strict manifest: {manifest_path}",
        f"- realized_as_of: {realized_as_of}",
        f"- snapshot rows requested: {requested_snapshot_count}",
        f"- snapshot rows succeeded: {successful_snapshot_count}",
        f"- snapshot rows failed: {failed_snapshot_count}",
        f"- required expiration outcome groups from manifest: {required_outcome_count}",
        f"- eligible realized outcome groups at cutoff: {eligible_required_outcome_count}",
        f"- future outcome groups excluded at cutoff: {future_required_outcome_count}",
        "",
    ]
    return "\n".join(context_lines) + report_markdown


def run_historical_effectiveness_evaluation(
    *,
    historical_data_root: str | Path,
    ticker: str,
    output_dir: str | Path,
    realized_as_of: str,
    manifest_path: str | Path | None = None,
    snapshot_dates: Sequence[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    quality_settings: OfflineScanQualitySettings | None = None,
    metric_columns: Sequence[str] | None = None,
    bucket_count: int = 10,
) -> dict[str, Path]:
    output_root = Path(output_dir).resolve(strict=False)
    output_root.mkdir(parents=True, exist_ok=True)

    resolved_manifest_path = _resolve_manifest_path(
        historical_data_root=historical_data_root,
        ticker=ticker,
        output_dir=output_root,
        manifest_path=manifest_path,
        snapshot_dates=snapshot_dates,
        start_date=start_date,
        end_date=end_date,
    )

    candidates_path = output_root / "historical_candidates.csv"
    scan_summary_path = output_root / "historical_scan_summary.csv"
    realized_underlying_path = output_root / "realized_underlying.csv"
    realized_outcomes_path = output_root / "realized_outcomes.csv"
    predictions_path = output_root / "probability_predictions.csv"
    calibration_summary_path = output_root / "calibration_summary.csv"
    calibration_bins_path = output_root / "calibration_bins.csv"
    calibration_observations_path = output_root / "calibration_observations.csv"
    effectiveness_summary_path = output_root / "effectiveness_summary.csv"
    effectiveness_observations_path = output_root / "effectiveness_observations.csv"
    metric_buckets_path = output_root / "effectiveness_metric_buckets.csv"
    segment_summary_path = output_root / "effectiveness_segment_summary.csv"
    execution_sensitivity_path = output_root / "effectiveness_execution_sensitivity.csv"
    tail_concentration_path = output_root / "effectiveness_tail_concentration.csv"
    report_path = output_root / "historical_effectiveness_report.md"

    candidates, scan_summary = run_historical_snapshot_scan(
        resolved_manifest_path,
        output_path=candidates_path,
        summary_output_path=scan_summary_path,
        quality_settings=quality_settings,
    )
    if candidates.empty:
        raise ValueError(
            "Historical scan produced no candidates. Review historical_scan_summary.csv before "
            "running effectiveness analysis."
        )

    write_trading_foundation_realized_underlying(
        historical_data_root,
        ticker=ticker,
        manifest_path=resolved_manifest_path,
        realized_as_of=realized_as_of,
        output_path=realized_underlying_path,
    )

    outcome_artifacts = materialize_realized_outcomes_from_snapshot_manifest(
        manifest_path=resolved_manifest_path,
        realized_underlying_paths=[realized_underlying_path],
        realized_as_of=realized_as_of,
    )
    write_realized_outcomes(outcome_artifacts.outcomes, realized_outcomes_path)

    effectiveness = evaluate_scanner_effectiveness(
        candidates,
        outcome_artifacts.outcomes,
        metric_columns=metric_columns,
        bucket_count=bucket_count,
        drop_missing_outcomes=True,
        allow_shared_outcome_keys=True,
    )

    summary_with_context = effectiveness.summary.copy()
    summary_with_context["required_outcome_group_count"] = int(
        len(outcome_artifacts.required_observations)
    )
    summary_with_context["eligible_required_outcome_group_count"] = int(
        len(outcome_artifacts.eligible_required_observations)
    )
    summary_with_context["future_required_outcome_group_count"] = int(
        len(outcome_artifacts.future_required_observations)
    )
    summary_with_context["requested_snapshot_count"] = int(len(scan_summary))
    summary_with_context["failed_snapshot_count"] = (
        int((scan_summary["status"] == "failed").sum()) if not scan_summary.empty else 0
    )

    report_markdown = _prepend_run_context(
        effectiveness.report_markdown,
        manifest_path=resolved_manifest_path,
        realized_as_of=realized_as_of,
        historical_data_root=historical_data_root,
        ticker=ticker,
        scan_summary=scan_summary,
        required_outcome_count=len(outcome_artifacts.required_observations),
        eligible_required_outcome_count=len(outcome_artifacts.eligible_required_observations),
        future_required_outcome_count=len(outcome_artifacts.future_required_observations),
    )

    _write_csv(effectiveness.predictions, predictions_path)
    _write_csv(effectiveness.calibration_summary, calibration_summary_path)
    _write_csv(effectiveness.calibration_bins, calibration_bins_path)
    _write_csv(effectiveness.calibration_observations, calibration_observations_path)
    _write_csv(summary_with_context, effectiveness_summary_path)
    _write_csv(effectiveness.observations, effectiveness_observations_path)
    _write_csv(effectiveness.metric_buckets, metric_buckets_path)
    _write_csv(effectiveness.segment_summary, segment_summary_path)
    _write_csv(effectiveness.execution_sensitivity, execution_sensitivity_path)
    _write_csv(effectiveness.tail_concentration, tail_concentration_path)
    _write_text(report_markdown, report_path)

    return {
        "manifest": resolved_manifest_path,
        "candidates": candidates_path,
        "scan_summary": scan_summary_path,
        "realized_underlying": realized_underlying_path,
        "realized_outcomes": realized_outcomes_path,
        "predictions": predictions_path,
        "calibration_summary": calibration_summary_path,
        "calibration_bins": calibration_bins_path,
        "calibration_observations": calibration_observations_path,
        "effectiveness_summary": effectiveness_summary_path,
        "effectiveness_observations": effectiveness_observations_path,
        "metric_buckets": metric_buckets_path,
        "segment_summary": segment_summary_path,
        "execution_sensitivity": execution_sensitivity_path,
        "tail_concentration": tail_concentration_path,
        "report": report_path,
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for the historical effectiveness study workflow."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the maintained strict historical scanner against canonical Trading Foundation "
            "snapshot and EOD artifacts, then evaluate calibration and expiration-held "
            "effectiveness without changing the baseline ranking."
        )
    )
    parser.add_argument(
        "--historical-data-root",
        required=True,
        help="Canonical Trading Foundation historical_data root",
    )
    parser.add_argument("--ticker", required=True, help="Underlying ticker, such as SPY")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for all intermediate and final historical effectiveness artifacts",
    )
    parser.add_argument(
        "--realized-as-of",
        required=True,
        help=(
            "Explicit date or timestamp cutoff used to decide which expiration outcomes are "
            "already realized. Use a concrete value for reproducible research runs."
        ),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Optional existing strict historical snapshot manifest. If omitted, the CLI will "
            "build one from canonical Trading Foundation snapshot files using the snapshot "
            "selection arguments below."
        ),
    )
    parser.add_argument(
        "--snapshot-date",
        dest="snapshot_dates",
        action="append",
        default=None,
        help="Optional snapshot date to include when building a manifest from canonical files",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Optional inclusive start date when building a manifest from canonical files",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Optional inclusive end date when building a manifest from canonical files",
    )
    parser.add_argument(
        "--metric-column",
        dest="metric_columns",
        action="append",
        default=None,
        help=(
            "Metric column to rank into effectiveness buckets. Repeat to add more columns. "
            "Defaults to ranking_score, expected_value, and probability_of_profit."
        ),
    )
    parser.add_argument(
        "--bucket-count",
        type=int,
        default=10,
        help="Requested number of ordered effectiveness buckets for each metric; default 10",
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
    """Parse arguments, run the effectiveness workflow, and print key output locations."""
    args = build_parser().parse_args(argv)
    output_paths = run_historical_effectiveness_evaluation(
        historical_data_root=args.historical_data_root,
        ticker=args.ticker,
        output_dir=args.output_dir,
        realized_as_of=args.realized_as_of,
        manifest_path=args.manifest,
        snapshot_dates=args.snapshot_dates,
        start_date=args.start_date,
        end_date=args.end_date,
        quality_settings=_build_quality_settings(args),
        metric_columns=args.metric_columns,
        bucket_count=args.bucket_count,
    )

    summary = pd.read_csv(output_paths["effectiveness_summary"])
    summary_row = summary.iloc[0]
    print("Historical effectiveness evaluation complete.")
    print(
        "Summary: "
        f"evaluated_opportunities={int(summary_row['evaluated_opportunity_count'])}, "
        f"evaluated_outcomes={int(summary_row['evaluated_outcome_count'])}, "
        f"mean_realized_pnl_executable={summary_row['mean_realized_pnl_executable']:.6f}, "
        f"ranking_score_auc_realized_profit={summary_row['ranking_score_auc_realized_profit']:.6f}"
    )
    print(f"Manifest: {output_paths['manifest']}")
    print(f"Candidates: {output_paths['candidates']}")
    print(f"Realized outcomes: {output_paths['realized_outcomes']}")
    print(f"Effectiveness summary: {output_paths['effectiveness_summary']}")
    print(f"Report: {output_paths['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
