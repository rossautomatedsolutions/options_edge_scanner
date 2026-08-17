from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.cli.probability_calibration_eval import main


PREDICTION_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_probability_predictions.csv"
OUTCOME_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_realized_outcomes.csv"


def test_probability_calibration_cli_writes_machine_readable_outputs(tmp_path: Path) -> None:
    summary_path = tmp_path / "calibration_summary.csv"
    bins_path = tmp_path / "calibration_bins.csv"
    observations_path = tmp_path / "calibration_observations.csv"

    exit_code = main(
        [
            "--predictions",
            str(PREDICTION_FIXTURE_PATH),
            "--outcomes",
            str(OUTCOME_FIXTURE_PATH),
            "--summary-output",
            str(summary_path),
            "--bins-output",
            str(bins_path),
            "--observations-output",
            str(observations_path),
            "--bin-count",
            "4",
        ]
    )

    assert exit_code == 0
    assert summary_path.exists()
    assert bins_path.exists()
    assert observations_path.exists()

    summary = pd.read_csv(summary_path)
    bins = pd.read_csv(bins_path)
    observations = pd.read_csv(observations_path)

    assert len(summary) == 1
    assert len(bins) == 4
    assert len(observations) == 4
    assert "brier_score" in summary.columns
    assert "observed_event_rate" in bins.columns
    assert "realized_event" in observations.columns


def test_probability_calibration_cli_help_includes_expected_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["--help"])

    captured = capsys.readouterr()
    assert "--predictions" in captured.out
    assert "--outcomes" in captured.out
    assert "--summary-output" in captured.out
    assert "--bins-output" in captured.out
