from __future__ import annotations

import json
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
    assert len(output_frame) == 4
    assert output_frame["expected_value"].is_monotonic_decreasing
    assert output_frame.iloc[0]["spread_type"] == "bear_put_debit"
    assert output_frame.iloc[0]["lower_strike"] == 100.0
    assert output_frame.iloc[0]["upper_strike"] == 110.0
    assert output_frame.iloc[0]["expected_value"] < output_frame.iloc[0]["theoretical_expected_value"]


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
    assert "--max-spread-market-width-pct" in captured.out
    assert "--report-output" in captured.out


def test_offline_scan_cli_writes_machine_readable_report(tmp_path: Path) -> None:
    output_path = tmp_path / "offline_scan_sample.csv"
    report_path = tmp_path / "offline_scan_report.json"

    exit_code = main(
        [
            "--input",
            str(FIXTURE_PATH),
            "--output",
            str(output_path),
            "--report-output",
            str(report_path),
            "--as-of",
            "2026-01-02",
        ]
    )

    assert exit_code == 0
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "offline_scan"
    assert report["counts"]["prepared_quote_count"] == 8
    assert report["counts"]["generated_spread_count"] == 8
    assert report["counts"]["ranked_candidate_count"] == 4
    assert report["result_summary"]["row_count"] == 4
    assert report["top_opportunities"][0]["selection_rank"] == 1


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
            "--spot-observed-at",
            "2026-01-02T15:30:00Z",
        ]
    )

    assert exit_code == 0
    output_frame = pd.read_csv(output_path)
    assert len(output_frame) == 4
    assert set(output_frame["underlying_price_source"]) == {"user.override"}
    assert set(output_frame["underlying_price_observed_at"]) == {"2026-01-02 15:30:00"}


def test_offline_scan_cli_infers_provenance_from_metadata_sidecar(tmp_path: Path) -> None:
    input_path = tmp_path / "sidecar_only.csv"
    output_path = tmp_path / "sidecar_output.csv"

    option_quotes = load_option_quotes(FIXTURE_PATH).drop(
        columns=["quote_observed_at", "underlying_price_observed_at", "underlying_price_source"]
    )
    option_quotes.to_csv(input_path, index=False)
    metadata_path = input_path.with_suffix(input_path.suffix + ".meta.json")
    metadata_path.write_text(
        json.dumps(
            {
                "fetched_at_utc": "2026-01-02T15:30:00Z",
                "underlying_price_observed_at": "2026-01-02T15:30:00Z",
                "underlying_price_source": "sidecar.test",
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--as-of",
            "2026-01-02",
        ]
    )

    assert exit_code == 0
    output_frame = pd.read_csv(output_path)
    assert set(output_frame["source_metadata_path"]) == {str(metadata_path)}
    assert set(output_frame["underlying_price_source"]) == {"sidecar.test"}


def test_offline_scan_cli_requires_provenance_unless_unsafe_override_is_set(tmp_path: Path) -> None:
    input_path = tmp_path / "missing_provenance.csv"
    output_path = tmp_path / "unsafe_output.csv"

    option_quotes = load_option_quotes(FIXTURE_PATH).drop(
        columns=["quote_observed_at", "underlying_price_observed_at", "underlying_price_source"]
    )
    option_quotes.to_csv(input_path, index=False)

    with pytest.raises(ValueError, match="quote_observed_at provenance"):
        main(
            [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--as-of",
                "2026-01-02",
            ]
        )

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--as-of",
            "2026-01-02",
            "--allow-unsafe-as-of",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()


def test_offline_scan_cli_spot_override_clears_stale_spot_provenance_when_unsafe(tmp_path: Path) -> None:
    input_path = tmp_path / "spot_override.csv"
    output_path = tmp_path / "spot_override_output.csv"

    load_option_quotes(FIXTURE_PATH).to_csv(input_path, index=False)

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--as-of",
            "2026-01-02",
            "--spot",
            "123.45",
            "--allow-unsafe-as-of",
        ]
    )

    assert exit_code == 0
    output_frame = pd.read_csv(output_path)
    assert set(output_frame["underlying_price"]) == {123.45}
    assert set(output_frame["underlying_price_source"]) == {"user.override"}
    assert output_frame["underlying_price_observed_at"].isna().all()
