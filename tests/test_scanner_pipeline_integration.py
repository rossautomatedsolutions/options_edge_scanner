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
        "underlying_price",
        "implied_volatility",
        "probability_of_profit",
        "expected_value",
        "edge_pct",
        "ev_method",
    }
    assert required_columns.issubset(opportunities.columns)

    assert len(opportunities) == 9

    top_row = opportunities.iloc[0]
    assert top_row["ticker"] == "XYZ"
    assert top_row["spread_type"] == "bear_put_debit"
    assert top_row["lower_strike"] == 100.0
    assert top_row["upper_strike"] == 110.0
    assert top_row["days_to_expiration"] == 42.0
    assert top_row["ev_method"] == "breakeven_binary_mvp"
    assert top_row["probability_of_profit"] == pytest.approx(0.8608285656, abs=1e-9)
    assert top_row["expected_value"] == pytest.approx(6.5582856562, abs=1e-9)
    assert top_row["edge_pct"] == pytest.approx(327.9142828, abs=1e-7)

    fifth_row = opportunities.iloc[4]
    assert fifth_row["spread_type"] == "bear_put_debit"
    assert fifth_row["lower_strike"] == 100.0
    assert fifth_row["upper_strike"] == 105.0
    assert fifth_row["probability_of_profit"] == pytest.approx(0.7068696790, abs=1e-9)
    assert fifth_row["expected_value"] == pytest.approx(2.1843483949, abs=1e-9)

    assert opportunities["expected_value"].is_monotonic_decreasing
