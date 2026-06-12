from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from options_edge_scanner.cli.yahoo_option_chain_ingest import build_parser, main
from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.yahoo_ingestion import YahooIngestionError, ingest_yahoo_option_chain


def _build_chain(calls: pd.DataFrame, puts: pd.DataFrame) -> Any:
    return SimpleNamespace(calls=calls, puts=puts)


class _FakeTicker:
    def __init__(
        self,
        symbol: str,
        *,
        options: list[str],
        chains: dict[str, Any],
        history_frame: pd.DataFrame,
    ) -> None:
        self.symbol = symbol
        self.options = options
        self._chains = chains
        self._history_frame = history_frame

    def option_chain(self, expiration: str) -> Any:
        return self._chains[expiration]

    def history(self, period: str = "1d") -> pd.DataFrame:
        return self._history_frame.copy()


class _FakeYFinanceModule:
    __version__ = "99.0-test"

    def __init__(
        self,
        *,
        options: list[str],
        chains: dict[str, Any],
        history_frame: pd.DataFrame | None = None,
    ) -> None:
        self._options = options
        self._chains = chains
        self._history_frame = history_frame or pd.DataFrame({"Close": [101.25]})

    def Ticker(self, symbol: str) -> _FakeTicker:  # noqa: N802 - match third-party API
        return _FakeTicker(
            symbol,
            options=self._options,
            chains=self._chains,
            history_frame=self._history_frame,
        )


def _sample_calls() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "contractSymbol": ["SPY260620C00550000", "SPY260620C00560000"],
            "strike": [550.0, 560.0],
            "bid": [4.8, 2.2],
            "ask": [5.2, 2.6],
            "impliedVolatility": [0.18, 0.19],
        }
    )


def _sample_puts() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "contractSymbol": ["SPY260620P00550000", "SPY260620P00540000"],
            "strike": [550.0, 540.0],
            "bid": [6.1, 3.1],
            "ask": [6.5, 3.5],
            "impliedVolatility": [0.2, 0.21],
        }
    )


def _fixed_now() -> datetime:
    return datetime(2026, 6, 12, 15, 30, tzinfo=timezone.utc)


def test_ingestion_writes_normalized_csv_and_metadata_sidecar(tmp_path: Path) -> None:
    fake_yf = _FakeYFinanceModule(
        options=["2026-06-20"],
        chains={"2026-06-20": _build_chain(_sample_calls(), _sample_puts())},
    )

    result = ingest_yahoo_option_chain(
        ticker="spy",
        requested_expiration="2026-06-20",
        output_dir=tmp_path,
        write_raw_json=True,
        yf_module=fake_yf,
        now=_fixed_now(),
    )

    assert result.csv_path.exists()
    assert result.metadata_path.exists()
    quotes = load_option_quotes(result.csv_path)
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

    assert list(quotes.columns) == [
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
    assert len(quotes) == 4
    assert set(quotes["type"].tolist()) == {"call", "put"}
    assert quotes["ticker"].tolist() == ["SPY", "SPY", "SPY", "SPY"]
    assert metadata["source_vendor"] == "yahoo_finance"
    assert metadata["ticker_normalized"] == "SPY"
    assert metadata["expiration_resolved"] == "2026-06-20"
    assert metadata["calls_row_count"] == 2
    assert metadata["puts_row_count"] == 2
    assert metadata["normalized_row_count"] == 4
    assert metadata["raw_payload_written"] is True
    assert metadata["cache_hit"] is False


def test_ingestion_uses_nearest_expiration_when_requested(tmp_path: Path) -> None:
    fake_yf = _FakeYFinanceModule(
        options=["2026-07-17", "2026-06-20"],
        chains={"2026-06-20": _build_chain(_sample_calls(), _sample_puts())},
    )

    result = ingest_yahoo_option_chain(
        ticker="SPY",
        requested_expiration="nearest",
        output_dir=tmp_path,
        yf_module=fake_yf,
        now=_fixed_now(),
    )

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["expiration_requested"] == "nearest"
    assert metadata["expiration_resolved"] == "2026-06-20"
    assert result.csv_path.name == "SPY_2026-06-20_yahoo.csv"


def test_ingestion_fails_for_missing_requested_expiration(tmp_path: Path) -> None:
    fake_yf = _FakeYFinanceModule(
        options=["2026-06-20"],
        chains={"2026-06-20": _build_chain(_sample_calls(), _sample_puts())},
    )

    with pytest.raises(YahooIngestionError, match="Requested expiration 2026-07-17 is not available"):
        ingest_yahoo_option_chain(
            ticker="SPY",
            requested_expiration="2026-07-17",
            output_dir=tmp_path,
            yf_module=fake_yf,
            now=_fixed_now(),
        )


def test_ingestion_fails_clearly_when_yfinance_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from options_edge_scanner import yahoo_ingestion

    def _raise_import_error(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(yahoo_ingestion.importlib, "import_module", _raise_import_error)

    with pytest.raises(YahooIngestionError, match="optional 'yfinance' dependency"):
        ingest_yahoo_option_chain(
            ticker="SPY",
            requested_expiration="nearest",
            output_dir=tmp_path,
        )


def test_ingestion_refuses_to_overwrite_existing_csv_without_flag(tmp_path: Path) -> None:
    fake_yf = _FakeYFinanceModule(
        options=["2026-06-20"],
        chains={"2026-06-20": _build_chain(_sample_calls(), _sample_puts())},
    )

    ingest_yahoo_option_chain(
        ticker="SPY",
        requested_expiration="2026-06-20",
        output_dir=tmp_path,
        yf_module=fake_yf,
        now=_fixed_now(),
    )

    with pytest.raises(YahooIngestionError, match="already exists"):
        ingest_yahoo_option_chain(
            ticker="SPY",
            requested_expiration="2026-06-20",
            output_dir=tmp_path,
            yf_module=fake_yf,
            now=_fixed_now(),
        )


def test_ingestion_fails_for_empty_option_chain(tmp_path: Path) -> None:
    fake_yf = _FakeYFinanceModule(
        options=["2026-06-20"],
        chains={"2026-06-20": _build_chain(pd.DataFrame(), pd.DataFrame())},
    )

    with pytest.raises(YahooIngestionError, match="empty option chain"):
        ingest_yahoo_option_chain(
            ticker="SPY",
            requested_expiration="2026-06-20",
            output_dir=tmp_path,
            yf_module=fake_yf,
            now=_fixed_now(),
        )


def test_cli_help_includes_expected_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="0"):
        build_parser().parse_args(["--help"])

    captured = capsys.readouterr()
    assert "--ticker" in captured.out
    assert "--expiration" in captured.out
    assert "--output" in captured.out
    assert "--use-cache" in captured.out


def test_cli_main_writes_files_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_yf = _FakeYFinanceModule(
        options=["2026-06-20"],
        chains={"2026-06-20": _build_chain(_sample_calls(), _sample_puts())},
    )
    from options_edge_scanner import yahoo_ingestion

    monkeypatch.setattr(yahoo_ingestion, "_utc_now", _fixed_now)
    monkeypatch.setattr(yahoo_ingestion, "_import_yfinance", lambda: fake_yf)

    exit_code = main(
        [
            "--ticker",
            "SPY",
            "--expiration",
            "2026-06-20",
            "--output-dir",
            str(tmp_path),
            "--write-raw-json",
        ]
    )

    assert exit_code == 0
    quotes = load_option_quotes(tmp_path / "SPY_2026-06-20_yahoo.csv")
    assert len(quotes) == 4
