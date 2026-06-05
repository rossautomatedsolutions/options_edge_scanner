from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


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

    assert len(opportunities) == 9
    assert opportunities.iloc[0]["spread_type"] == "bear_put_debit"
    assert opportunities.iloc[0]["expected_value"] == pytest.approx(6.5582856562, abs=1e-9)
