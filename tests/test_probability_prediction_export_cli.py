from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.cli.export_probability_predictions import main
from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def test_probability_prediction_export_cli_writes_validated_predictions(tmp_path: Path) -> None:
    opportunities_path = tmp_path / "opportunities.csv"
    output_path = tmp_path / "predictions.csv"

    opportunities = build_scanner_opportunities(load_option_quotes(FIXTURE_PATH), as_of="2026-01-02")
    opportunities["snapshot_id"] = "XYZ_20260102T153000Z_2026-02-13"
    opportunities.to_csv(opportunities_path, index=False)

    exit_code = main(
        [
            "--opportunities",
            str(opportunities_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()

    exported = pd.read_csv(output_path)
    assert len(exported) == 4
    assert {"prediction_id", "predicted_probability", "required_outcome_key"}.issubset(
        exported.columns
    )
    assert exported["prediction_id"].is_unique


def test_probability_prediction_export_cli_rejects_null_like_snapshot_ids(tmp_path: Path) -> None:
    opportunities_path = tmp_path / "opportunities_missing_snapshot.csv"
    output_path = tmp_path / "predictions.csv"

    opportunities = build_scanner_opportunities(load_option_quotes(FIXTURE_PATH), as_of="2026-01-02")
    opportunities["snapshot_id"] = pd.NA
    opportunities.to_csv(opportunities_path, index=False)

    with pytest.raises(ValueError, match="non-empty snapshot_id"):
        main(
            [
                "--opportunities",
                str(opportunities_path),
                "--output",
                str(output_path),
            ]
        )


def test_probability_prediction_export_cli_help_includes_expected_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["--help"])

    captured = capsys.readouterr()
    assert "--opportunities" in captured.out
    assert "--output" in captured.out
