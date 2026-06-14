from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities
from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"
ALIAS_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain_aliases.csv"


def test_load_option_quotes_reads_existing_csv_fixture() -> None:
    option_quotes = load_option_quotes(FIXTURE_PATH)

    assert list(option_quotes.columns) == [
        "ticker",
        "expiration",
        "strike",
        "type",
        "bid",
        "ask",
        "mid",
        "implied_vol",
        "underlying_price",
    ]
    assert len(option_quotes) == 8
    assert option_quotes["ticker"].tolist()[:2] == ["XYZ", "XYZ"]
    assert pd.api.types.is_datetime64_any_dtype(option_quotes["expiration"])


def test_load_option_quotes_normalizes_documented_safe_alias_columns() -> None:
    option_quotes = load_option_quotes(ALIAS_FIXTURE_PATH)

    assert list(option_quotes.columns) == [
        "ticker",
        "expiration",
        "strike",
        "type",
        "bid",
        "ask",
        "mid",
        "implied_vol",
        "underlying_price",
    ]
    assert len(option_quotes) == 8
    assert option_quotes["ticker"].tolist()[:2] == ["XYZ", "XYZ"]
    assert option_quotes["type"].tolist()[:2] == ["call", "call"]
    assert option_quotes["strike"].tolist()[:3] == [95, 100, 105]
    assert option_quotes["implied_vol"].tolist()[:2] == [0.24, 0.23]
    assert pd.api.types.is_datetime64_any_dtype(option_quotes["expiration"])


def test_load_option_quotes_raises_for_missing_required_columns(tmp_path: Path) -> None:
    broken_path = tmp_path / "missing_columns.csv"
    pd.DataFrame(
        {
            "ticker": ["XYZ"],
            "expiration": ["2026-02-13"],
            "strike": [100],
            "type": ["call"],
            "bid": [1.0],
            "ask": [1.2],
            "mid": [1.1],
            "underlying_price": [100.0],
        }
    ).to_csv(broken_path, index=False)

    with pytest.raises(ValueError, match="Missing required OptionQuoteRow columns: implied_vol"):
        load_option_quotes(broken_path)


def test_loaded_fixture_feeds_scanner_pipeline() -> None:
    option_quotes = load_option_quotes(FIXTURE_PATH)

    opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")

    assert len(opportunities) == 7
    assert opportunities.iloc[0]["spread_type"] == "bear_put_debit"
    assert opportunities.iloc[0]["expected_value"] == pytest.approx(6.5582856562, abs=1e-9)


def test_alias_fixture_feeds_scanner_pipeline() -> None:
    option_quotes = load_option_quotes(ALIAS_FIXTURE_PATH)

    opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")

    assert len(opportunities) > 0
    assert opportunities.iloc[0]["ticker"] == "XYZ"
    assert {"bear_put_debit", "bull_call_debit"}.issuperset(set(opportunities["spread_type"].unique()))
    assert opportunities["expected_value"].is_monotonic_decreasing


def test_build_scanner_opportunities_filters_far_from_spot_and_high_debit_candidates() -> None:
    option_quotes = pd.concat(
        [
            load_option_quotes(FIXTURE_PATH),
            pd.DataFrame(
                {
                    "ticker": ["XYZ", "XYZ"],
                    "expiration": ["2026-02-13", "2026-02-13"],
                    "strike": [50.0, 60.0],
                    "type": ["call", "call"],
                    "bid": [51.0, 42.0],
                    "ask": [53.0, 44.0],
                    "mid": [52.0, 43.0],
                    "implied_vol": [0.20, 0.20],
                    "underlying_price": [100.0, 100.0],
                }
            ),
        ],
        ignore_index=True,
    )

    default_opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")
    relaxed_opportunities = build_scanner_opportunities(
        option_quotes,
        as_of="2026-01-02",
        quality_settings=OfflineScanQualitySettings(
            max_abs_moneyness_pct=1.0,
            max_debit_fraction_of_width=0.95,
            max_bid_ask_spread_pct=0.25,
        ),
    )

    assert not default_opportunities.empty
    assert ((default_opportunities["lower_strike"] == 50.0) & (default_opportunities["upper_strike"] == 60.0)).sum() == 0
    assert ((relaxed_opportunities["lower_strike"] == 50.0) & (relaxed_opportunities["upper_strike"] == 60.0)).sum() == 1


def test_build_scanner_opportunities_allows_near_spot_valid_calls_and_puts() -> None:
    option_quotes = pd.DataFrame(
        {
            "ticker": ["XYZ"] * 8,
            "expiration": ["2026-02-13"] * 8,
            "strike": [95.0, 100.0, 105.0, 110.0, 95.0, 100.0, 105.0, 110.0],
            "type": ["call", "call", "call", "call", "put", "put", "put", "put"],
            "bid": [6.8, 5.3, 3.8, 3.3, 1.3, 2.5, 3.8, 4.5],
            "ask": [7.2, 5.7, 4.2, 3.7, 1.7, 2.9, 4.2, 4.9],
            "mid": [7.0, 5.5, 4.0, 3.5, 1.5, 2.7, 4.0, 4.7],
            "implied_vol": [0.16, 0.15, 0.14, 0.13, 0.16, 0.17, 0.18, 0.19],
            "underlying_price": [100.0] * 8,
        }
    )

    opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")

    assert not opportunities.empty
    assert "bull_call_debit" in set(opportunities["spread_type"])
    assert "bear_put_debit" in set(opportunities["spread_type"])
