from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.cli.offline_scan import main
from options_edge_scanner.scanner.engine import SCANNER_OUTPUT_COLUMNS


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def test_offline_scan_cli_writes_ranked_output(tmp_path: Path) -> None:
    output_path = tmp_path / "offline_scan_sample.csv"

    exit_code = main(
        [
            "--input",
            str(FIXTURE_PATH),
            "--output",
            str(output_path),
            "--as-of",
            "2026-01-02",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()

    output_frame = pd.read_csv(output_path)

    assert list(output_frame.columns) == SCANNER_OUTPUT_COLUMNS
    assert len(output_frame) == 9


def test_offline_scan_cli_help_includes_expected_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["--help"])

    captured = capsys.readouterr()

    assert "research-only deterministic scanner" in captured.out
    assert "--input" in captured.out
    assert "--output" in captured.out
    assert "--as-of" in captured.out
