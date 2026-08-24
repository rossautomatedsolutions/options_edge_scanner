from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.effectiveness import evaluate_scanner_effectiveness
from options_edge_scanner.scanner.engine import build_scanner_opportunities


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def _build_opportunities() -> pd.DataFrame:
    opportunities = build_scanner_opportunities(
        load_option_quotes(FIXTURE_PATH),
        as_of="2026-01-02",
    )
    opportunities = opportunities.copy()
    opportunities["snapshot_id"] = "xyz-20260102-153000"
    return opportunities


def _clone_opportunities_with_expiration(
    opportunities: pd.DataFrame,
    *,
    expiration: str,
    snapshot_id: str,
    quote_observed_at: str,
) -> pd.DataFrame:
    cloned = opportunities.copy()
    cloned["expiration"] = expiration
    cloned["snapshot_id"] = snapshot_id
    cloned["quote_observed_at"] = quote_observed_at
    cloned["as_of"] = quote_observed_at
    return cloned


def _build_realized_outcomes(terminal_price: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "outcome_id": "outcome::XYZ|2026-02-13|expiration|terminal_underlying_price",
                "required_outcome_key": "XYZ|2026-02-13|expiration|terminal_underlying_price",
                "ticker": "XYZ",
                "expiration": "2026-02-13",
                "required_outcome_horizon": "expiration",
                "realized_outcome_measure": "terminal_underlying_price",
                "realized_terminal_underlying_price": terminal_price,
                "realized_outcome_observed_at": "2026-02-13T20:00:00Z",
                "realized_outcome_source": "fixture.expiration",
            }
        ]
    )


def test_effectiveness_evaluation_labels_realized_expiration_payoffs_correctly() -> None:
    opportunities = _build_opportunities()
    outcomes = _build_realized_outcomes(terminal_price=93.0)

    artifacts = evaluate_scanner_effectiveness(
        opportunities,
        outcomes,
        drop_missing_outcomes=True,
    )

    observations = artifacts.observations
    assert len(observations) == len(opportunities)

    bear_put_row = observations.loc[
        (observations["spread_type"] == "bear_put_debit")
        & (observations["lower_strike"] == 100.0)
        & (observations["upper_strike"] == 110.0)
    ].iloc[0]
    bull_call_row = observations.loc[
        (observations["spread_type"] == "bull_call_debit")
        & (observations["lower_strike"] == 95.0)
        & (observations["upper_strike"] == 100.0)
    ].iloc[0]

    assert bear_put_row["spread_expiration_value"] == pytest.approx(10.0)
    assert bear_put_row["realized_event"] == 1
    assert bear_put_row["realized_pnl_executable"] == pytest.approx(
        10.0 - float(bear_put_row["debit"]) - 0.05,
        abs=1e-12,
    )

    assert bull_call_row["spread_expiration_value"] == pytest.approx(0.0)
    assert bull_call_row["realized_event"] == 0
    assert bull_call_row["realized_pnl_executable"] == pytest.approx(
        -float(bull_call_row["debit"]) - 0.05,
        abs=1e-12,
    )


def test_effectiveness_evaluation_emits_bucket_and_calibration_artifacts() -> None:
    opportunities = _build_opportunities()
    outcomes = _build_realized_outcomes(terminal_price=104.0)

    artifacts = evaluate_scanner_effectiveness(
        opportunities,
        outcomes,
        drop_missing_outcomes=True,
    )

    summary = artifacts.summary.iloc[0]
    assert summary["evaluated_opportunity_count"] == len(opportunities)
    assert summary["shared_outcome_key_count"] == 1
    assert {"ranking_score", "expected_value", "probability_of_profit"} == set(
        artifacts.metric_buckets["metric_name"]
    )
    assert {
        "quoted_mid",
        "baseline_executable",
        "displayed_ask",
    } == set(artifacts.execution_sensitivity["scenario_name"])
    assert not artifacts.calibration_summary.empty
    assert not artifacts.calibration_bins.empty
    assert "Historical Effectiveness Report" in artifacts.report_markdown


def test_effectiveness_evaluation_excludes_missing_outcomes_without_contaminating_metrics() -> None:
    base_opportunities = _build_opportunities()
    missing_opportunities = _clone_opportunities_with_expiration(
        base_opportunities,
        expiration="2026-02-20",
        snapshot_id="xyz-20260103-153000",
        quote_observed_at="2026-01-03T15:30:00Z",
    )
    opportunities = pd.concat([base_opportunities, missing_opportunities], ignore_index=True)
    outcomes = _build_realized_outcomes(terminal_price=104.0)

    artifacts = evaluate_scanner_effectiveness(
        opportunities,
        outcomes,
        drop_missing_outcomes=True,
        exclusion_details=pd.DataFrame(
            [
                {
                    "required_outcome_key": "XYZ|2026-02-20|expiration|terminal_underlying_price",
                    "exclusion_reason": "missing_realized_underlying",
                    "exclusion_detail": "Canonical realized EOD observation is unavailable.",
                    "required_event_date": "2026-02-20",
                    "issue_classification": "trading_day_absent_from_canonical_eod",
                    "previous_available_event_date": "2026-02-19",
                    "next_available_event_date": "2026-02-23",
                }
            ]
        ),
    )

    summary = artifacts.summary.iloc[0]
    assert int(summary["input_opportunity_count"]) == len(opportunities)
    assert int(summary["evaluated_opportunity_count"]) == len(base_opportunities)
    assert int(summary["excluded_opportunity_count"]) == len(missing_opportunities)
    assert int(summary["excluded_missing_realized_underlying_count"]) == len(missing_opportunities)
    assert summary["missing_realized_event_dates"] == "2026-02-20"
    assert int(summary["missing_realized_event_date_count"]) == 1
    assert summary["evaluation_status"] == "complete"
    assert summary["evaluation_coverage_rate"] == pytest.approx(
        len(base_opportunities) / len(opportunities),
        abs=1e-12,
    )

    assert len(artifacts.observations) == len(base_opportunities)
    assert len(artifacts.exclusions) == len(missing_opportunities)
    assert set(artifacts.exclusions["exclusion_reason"]) == {"missing_realized_underlying"}
    assert set(artifacts.exclusions["required_event_date"]) == {
        pd.Timestamp("2026-02-20")
    }
    assert artifacts.exclusions["previous_available_event_date"].dropna().unique().tolist() == [
        "2026-02-19"
    ]
    assert int(artifacts.calibration_summary.iloc[0]["prediction_count"]) == len(base_opportunities)
    assert int(
        artifacts.metric_buckets.loc[
            artifacts.metric_buckets["metric_name"] == "ranking_score",
            "observation_count",
        ].sum()
    ) == len(base_opportunities)
    assert not artifacts.execution_sensitivity["mean_realized_pnl"].isna().all()
    assert "2026-02-20" in artifacts.report_markdown


def test_effectiveness_evaluation_reports_insufficient_data_when_all_opportunities_are_unevaluable() -> None:
    opportunities = _build_opportunities()
    outcomes = _build_realized_outcomes(terminal_price=101.0).iloc[0:0].copy()

    artifacts = evaluate_scanner_effectiveness(
        opportunities,
        outcomes,
        drop_missing_outcomes=True,
        exclusion_details=pd.DataFrame(
            [
                {
                    "required_outcome_key": "XYZ|2026-02-13|expiration|terminal_underlying_price",
                    "exclusion_reason": "missing_realized_underlying",
                    "exclusion_detail": "Canonical realized EOD observation is unavailable.",
                    "required_event_date": "2026-02-13",
                }
            ]
        ),
    )

    summary = artifacts.summary.iloc[0]
    assert int(summary["evaluated_opportunity_count"]) == 0
    assert int(summary["excluded_opportunity_count"]) == len(opportunities)
    assert summary["evaluation_status"] == "insufficient_realized_outcome_data"
    assert summary["evaluation_coverage_rate"] == pytest.approx(0.0, abs=1e-12)
    assert artifacts.observations.empty
    assert len(artifacts.exclusions) == len(opportunities)
    assert artifacts.calibration_summary.empty
    assert artifacts.metric_buckets.empty
    assert artifacts.execution_sensitivity.empty
    assert "no evaluable opportunities had realized outcomes" in artifacts.report_markdown


def test_effectiveness_evaluation_can_drop_missing_outcomes_explicitly() -> None:
    opportunities = _build_opportunities()
    outcomes = _build_realized_outcomes(terminal_price=101.0).iloc[0:0].copy()

    with pytest.raises(ValueError, match="Missing realized outcomes"):
        evaluate_scanner_effectiveness(
            opportunities,
            outcomes,
            drop_missing_outcomes=False,
        )
