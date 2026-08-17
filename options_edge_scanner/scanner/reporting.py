"""Machine-readable report helpers for offline scanner runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from options_edge_scanner.scanner.engine import ScannerBuildArtifacts
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


def _format_timestamp_like(value: object) -> str | None:
    """Return one ISO-like string for timestamp/date-like values."""
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        return timestamp.isoformat()
    if timestamp.hour == 0 and timestamp.minute == 0 and timestamp.second == 0:
        return timestamp.strftime("%Y-%m-%d")
    return timestamp.isoformat()


def _top_opportunity_rows(opportunities: pd.DataFrame, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return a compact top-opportunity payload for one scan report."""
    if opportunities.empty:
        return []

    rows: list[dict[str, Any]] = []
    for row in opportunities.head(limit).to_dict("records"):
        rows.append(
            {
                "selection_rank": int(row["selection_rank"]),
                "ticker": str(row["ticker"]),
                "expiration": _format_timestamp_like(row["expiration"]),
                "spread_type": str(row["spread_type"]),
                "lower_strike": float(row["lower_strike"]),
                "upper_strike": float(row["upper_strike"]),
                "quoted_debit": float(row["quoted_debit"]),
                "entry_debit": float(row["debit"]),
                "theoretical_expected_value": float(row["theoretical_expected_value"]),
                "expected_value": float(row["expected_value"]),
                "probability_of_profit": float(row["probability_of_profit"]),
                "liquidity_score": float(row["liquidity_score"]),
            }
        )
    return rows


def build_scan_report(
    artifacts: ScannerBuildArtifacts,
    *,
    input_path: str | Path,
    output_path: str | Path,
    settings: OfflineScanQualitySettings,
    mode: str = "offline_scan",
) -> dict[str, Any]:
    """Build one machine-readable report for a completed offline scan."""
    opportunities = artifacts.opportunities.copy()
    probability_models = []
    if not opportunities.empty:
        probability_models = (
            opportunities.loc[:, ["probability_model_name", "probability_model_version"]]
            .drop_duplicates()
            .sort_values(["probability_model_name", "probability_model_version"], kind="stable")
            .to_dict("records")
        )

    result_summary = {
        "row_count": int(len(opportunities)),
        "mean_expected_value": (
            float(pd.to_numeric(opportunities["expected_value"], errors="coerce").mean())
            if not opportunities.empty
            else None
        ),
        "mean_theoretical_expected_value": (
            float(pd.to_numeric(opportunities["theoretical_expected_value"], errors="coerce").mean())
            if not opportunities.empty
            else None
        ),
        "mean_liquidity_score": (
            float(pd.to_numeric(opportunities["liquidity_score"], errors="coerce").mean())
            if not opportunities.empty
            else None
        ),
        "top_expected_value": (
            float(pd.to_numeric(opportunities["expected_value"], errors="coerce").max())
            if not opportunities.empty
            else None
        ),
    }

    warnings: list[str] = []
    if opportunities.empty:
        warnings.append("no_ranked_opportunities")

    return {
        "report_version": 1,
        "mode": mode,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "as_of": artifacts.as_of.isoformat(),
        "counts": {
            "prepared_quote_count": artifacts.prepared_quote_count,
            "filtered_quote_count": artifacts.filtered_quote_count,
            "generated_spread_count": artifacts.generated_spread_count,
            "filtered_spread_count": artifacts.filtered_spread_count,
            "dte_eligible_spread_count": artifacts.dte_eligible_spread_count,
            "ranked_candidate_count": artifacts.ranked_candidate_count,
        },
        "execution_assumptions": {
            "max_bid_ask_spread_pct": settings.max_bid_ask_spread_pct,
            "max_spread_market_width_pct": settings.max_spread_market_width_pct,
            "execution_slippage_floor": settings.execution_slippage_floor,
            "execution_slippage_cap": settings.execution_slippage_cap,
            "min_liquidity_score": settings.min_liquidity_score,
        },
        "selection_assumptions": {
            "min_expected_value": settings.min_expected_value,
            "min_probability_of_profit": settings.min_probability_of_profit,
            "top_n": settings.top_n,
            "max_positions_per_ticker": settings.max_positions_per_ticker,
            "max_positions_per_expiration": settings.max_positions_per_expiration,
        },
        "probability_models": probability_models,
        "result_summary": result_summary,
        "top_opportunities": _top_opportunity_rows(opportunities),
        "warnings": warnings,
    }


def write_scan_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write one report payload as JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return path
