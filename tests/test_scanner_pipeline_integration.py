from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.scanner.engine import build_scanner_opportunities


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def test_offline_scanner_pipeline_is_deterministic() -> None:
    option_quotes = pd.read_csv(FIXTURE_PATH, parse_dates=["expiration"])

    opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")

    required_columns = {
        "ticker",
        "expiration",
        "as_of",
        "snapshot_id",
        "snapshot_source",
        "quote_observed_at",
        "underlying_price_observed_at",
        "underlying_price_source",
        "probability_model_name",
        "probability_model_version",
        "predicted_event_name",
        "predicted_event_direction",
        "predicted_event_operator",
        "predicted_event_threshold",
        "predicted_event_horizon",
        "days_to_expiration",
        "option_type",
        "spread_type",
        "lower_strike",
        "upper_strike",
        "long_strike",
        "short_strike",
        "width",
        "debit",
        "max_profit",
        "max_loss",
        "quoted_debit",
        "theoretical_expected_value",
        "ranking_score",
        "selection_rank",
        "underlying_price",
        "implied_volatility",
        "probability_of_profit",
        "expected_value",
        "edge_pct",
        "ev_method",
    }
    assert required_columns.issubset(opportunities.columns)

    assert len(opportunities) == 4

    top_row = opportunities.iloc[0]
    assert top_row["ticker"] == "XYZ"
    assert top_row["spread_type"] == "bear_put_debit"
    assert top_row["lower_strike"] == 100.0
    assert top_row["upper_strike"] == 110.0
    assert str(top_row["as_of"]) == "2026-01-02 00:00:00"
    assert top_row["days_to_expiration"] == 42.0
    assert top_row["probability_model_name"] == "lognormal_breakeven"
    assert top_row["probability_model_version"] == "1"
    assert top_row["predicted_event_name"] == "terminal_underlying_crosses_spread_breakeven"
    assert top_row["predicted_event_direction"] == "below"
    assert top_row["predicted_event_operator"] == "<"
    assert top_row["predicted_event_horizon"] == "expiration"
    assert top_row["ev_method"] == "lognormal_vertical_exact"
    assert top_row["quoted_debit"] == pytest.approx(2.0, abs=1e-12)
    assert top_row["debit"] > top_row["quoted_debit"]
    assert top_row["probability_of_profit"] == pytest.approx(0.8530799542, abs=1e-9)
    assert top_row["theoretical_expected_value"] == pytest.approx(5.3720088049, abs=1e-9)
    assert top_row["expected_value"] == pytest.approx(5.1000182611, abs=1e-9)
    assert top_row["expected_value"] < top_row["theoretical_expected_value"]
    assert top_row["edge_pct"] == pytest.approx(224.4735690123, abs=1e-7)

    final_row = opportunities.iloc[3]
    assert final_row["spread_type"] == "bull_call_debit"
    assert final_row["lower_strike"] == 95.0
    assert final_row["upper_strike"] == 100.0
    assert final_row["probability_of_profit"] == pytest.approx(0.6870915018, abs=1e-9)
    assert final_row["expected_value"] == pytest.approx(1.3858222895, abs=1e-9)

    assert opportunities["ranking_score"].is_monotonic_decreasing
    assert opportunities["selection_rank"].tolist() == [1, 2, 3, 4]
