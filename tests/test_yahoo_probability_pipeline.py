from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from options_edge_scanner.cli.export_probability_predictions import run_probability_prediction_export
from options_edge_scanner.cli.offline_scan import run_offline_scan
from options_edge_scanner.yahoo_ingestion import ingest_yahoo_option_chain


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
        self._history_frame = history_frame if history_frame is not None else pd.DataFrame({"Close": [100.0]})

    def Ticker(self, symbol: str) -> _FakeTicker:  # noqa: N802 - third-party API shape
        return _FakeTicker(
            symbol,
            options=self._options,
            chains=self._chains,
            history_frame=self._history_frame,
        )


def _build_chain(calls: pd.DataFrame, puts: pd.DataFrame) -> Any:
    return SimpleNamespace(calls=calls, puts=puts)


def _sample_calls() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "contractSymbol": [
                "SPY260821C00095000",
                "SPY260821C00100000",
                "SPY260821C00105000",
                "SPY260821C00110000",
            ],
            "strike": [95.0, 100.0, 105.0, 110.0],
            "bid": [6.8, 5.3, 3.8, 3.3],
            "ask": [7.2, 5.7, 4.2, 3.7],
            "impliedVolatility": [0.16, 0.15, 0.14, 0.13],
        }
    )


def _sample_puts() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "contractSymbol": [
                "SPY260821P00095000",
                "SPY260821P00100000",
                "SPY260821P00105000",
                "SPY260821P00110000",
            ],
            "strike": [95.0, 100.0, 105.0, 110.0],
            "bid": [1.3, 2.5, 3.8, 4.5],
            "ask": [1.7, 2.9, 4.2, 4.9],
            "impliedVolatility": [0.16, 0.17, 0.18, 0.19],
        }
    )


def _fake_yfinance_module() -> _FakeYFinanceModule:
    history_index = pd.DatetimeIndex([pd.Timestamp("2026-08-17T20:00:00Z")])
    history_frame = pd.DataFrame({"Close": [100.0]}, index=history_index)
    return _FakeYFinanceModule(
        options=["2026-08-21"],
        chains={"2026-08-21": _build_chain(_sample_calls(), _sample_puts())},
        history_frame=history_frame,
    )


def _ingest_fresh_spy_snapshot(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    output_dir = tmp_path / "outputs" / "yahoo_option_chains" / "SPY"
    result = ingest_yahoo_option_chain(
        ticker="SPY",
        requested_expiration="2026-08-21",
        output_dir=output_dir,
        yf_module=_fake_yfinance_module(),
        now=datetime(2026, 8, 17, 23, 6, 11, 304419, tzinfo=timezone.utc),
    )
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    return result.csv_path, result.metadata_path, metadata


def test_fresh_yahoo_snapshot_id_propagates_through_scan_and_prediction_export(tmp_path: Path) -> None:
    input_path, metadata_path, metadata = _ingest_fresh_spy_snapshot(tmp_path)
    scan_output_path = tmp_path / "scan" / "spy_2026-08-21_opportunities.csv"
    predictions_output_path = tmp_path / "predictions" / "spy_2026-08-21_predictions.csv"

    assert metadata["snapshot_id"] == "SPY_20260817T230611.304419Z_2026-08-21"

    run_offline_scan(
        input_path=input_path,
        output_path=scan_output_path,
        as_of="2026-08-17",
    )
    opportunities = pd.read_csv(scan_output_path)

    assert not opportunities.empty
    assert set(opportunities["snapshot_id"]) == {metadata["snapshot_id"]}
    assert set(opportunities["source_metadata_path"]) == {str(metadata_path)}
    assert not opportunities["snapshot_id"].astype("string").str.contains("nan", case=False, na=False).any()

    run_probability_prediction_export(
        opportunities_path=scan_output_path,
        output_path=predictions_output_path,
    )
    predictions = pd.read_csv(predictions_output_path)

    assert not predictions.empty
    assert set(predictions["snapshot_id"]) == {metadata["snapshot_id"]}
    assert predictions["observation_group_id"].str.startswith(metadata["snapshot_id"] + "|").all()
    assert predictions["prediction_id"].str.startswith(metadata["snapshot_id"] + "|").all()
    assert not predictions["prediction_id"].str.contains("nan", case=False, na=False).any()
    assert not predictions["observation_group_id"].str.contains("nan", case=False, na=False).any()


@pytest.mark.parametrize("invalid_snapshot_id", [None, "nan"])
def test_offline_scan_rejects_missing_or_null_like_snapshot_id_from_yahoo_sidecar(
    tmp_path: Path,
    invalid_snapshot_id: str | None,
) -> None:
    input_path, metadata_path, metadata = _ingest_fresh_spy_snapshot(tmp_path)
    scan_output_path = tmp_path / "scan" / "spy_2026-08-21_opportunities.csv"

    metadata["snapshot_id"] = invalid_snapshot_id
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata sidecar must include a non-empty snapshot_id"):
        run_offline_scan(
            input_path=input_path,
            output_path=scan_output_path,
            as_of="2026-08-17",
        )
