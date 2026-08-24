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


def test_effectiveness_evaluation_can_drop_missing_outcomes_explicitly() -> None:
    opportunities = _build_opportunities()
    outcomes = _build_realized_outcomes(terminal_price=101.0).iloc[0:0].copy()

    with pytest.raises(ValueError, match="Missing realized outcomes"):
        evaluate_scanner_effectiveness(
            opportunities,
            outcomes,
            drop_missing_outcomes=False,
        )
