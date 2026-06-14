from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.cli.offline_scan import main
from options_edge_scanner.data.loader import load_option_quotes
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
    assert len(output_frame) == 7
    assert output_frame["expected_value"].is_monotonic_decreasing
    assert output_frame.iloc[0]["spread_type"] == "bear_put_debit"
    assert output_frame.iloc[0]["lower_strike"] == 100.0
    assert output_frame.iloc[0]["upper_strike"] == 110.0


def test_offline_scan_cli_help_includes_expected_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["--help"])

    captured = capsys.readouterr()

    assert "research-only deterministic scanner" in captured.out
    assert "--input" in captured.out
    assert "--output" in captured.out
    assert "--as-of" in captured.out
    assert "--spot" in captured.out
    assert "--max-abs-moneyness-pct" in captured.out


def test_offline_scan_cli_accepts_spot_override_for_missing_underlying_price(tmp_path: Path) -> None:
    input_path = tmp_path / "missing_underlying.csv"
    output_path = tmp_path / "offline_scan_missing_underlying.csv"

    option_quotes = load_option_quotes(FIXTURE_PATH).drop(columns=["underlying_price"])
    option_quotes.to_csv(input_path, index=False)

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--as-of",
            "2026-01-02",
            "--spot",
            "100",
        ]
    )

    assert exit_code == 0
    output_frame = pd.read_csv(output_path)
    assert len(output_frame) == 7
