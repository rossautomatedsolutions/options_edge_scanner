from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.cli.offline_batch_scan import SUMMARY_OUTPUT_COLUMNS, main
from options_edge_scanner.scanner.engine import SCANNER_OUTPUT_COLUMNS


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_offline_batch_scan_cli_writes_ranked_output(tmp_path: Path) -> None:
    output_path = tmp_path / "offline_batch_scan_sample.csv"
    manifest_path = tmp_path / "offline_scan_manifest.csv"
    pd.DataFrame(
        [
            {
                "input_path": str(FIXTURE_PATH),
                "output_path": str(output_path),
                "as_of": "2026-01-02",
            }
        ]
    ).to_csv(manifest_path, index=False)

    exit_code = main(["--manifest", str(manifest_path)])

    assert exit_code == 0
    assert output_path.exists()

    output_frame = pd.read_csv(output_path)

    assert list(output_frame.columns) == SCANNER_OUTPUT_COLUMNS
    assert len(output_frame) == 7


def test_offline_batch_scan_cli_writes_summary_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "offline_batch_scan_sample.csv"
    summary_path = tmp_path / "offline_batch_summary.csv"
    manifest_path = tmp_path / "offline_scan_manifest.csv"
    pd.DataFrame(
        [
            {
                "input_path": str(FIXTURE_PATH),
                "output_path": str(output_path),
                "as_of": "2026-01-02",
            }
        ]
    ).to_csv(manifest_path, index=False)

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    assert exit_code == 0
    assert summary_path.exists()

    summary_frame = pd.read_csv(summary_path)

    assert list(summary_frame.columns) == list(SUMMARY_OUTPUT_COLUMNS)
    assert len(summary_frame) == 1
    assert summary_frame.iloc[0]["status"] == "success"
    assert summary_frame.iloc[0]["row_count"] == 7
    assert pd.isna(summary_frame.iloc[0]["error_message"]) or summary_frame.iloc[0]["error_message"] == ""


def test_offline_batch_scan_cli_raises_for_missing_manifest_columns(tmp_path: Path) -> None:
    manifest_path = tmp_path / "broken_manifest.csv"
    pd.DataFrame(
        [
            {
                "input_path": str(FIXTURE_PATH),
                "output_path": str(tmp_path / "unused.csv"),
            }
        ]
    ).to_csv(manifest_path, index=False)

    with pytest.raises(ValueError, match="Missing required manifest columns: as_of"):
        main(["--manifest", str(manifest_path)])


def test_offline_batch_scan_cli_continues_and_records_failed_rows(tmp_path: Path) -> None:
    success_output_path = tmp_path / "offline_batch_scan_sample.csv"
    failed_output_path = tmp_path / "missing_output.csv"
    summary_path = tmp_path / "offline_batch_summary.csv"
    manifest_path = tmp_path / "offline_scan_manifest.csv"
    pd.DataFrame(
        [
            {
                "input_path": str(FIXTURE_PATH),
                "output_path": str(success_output_path),
                "as_of": "2026-01-02",
            },
            {
                "input_path": str(tmp_path / "does_not_exist.csv"),
                "output_path": str(failed_output_path),
                "as_of": "2026-01-02",
            },
        ]
    ).to_csv(manifest_path, index=False)

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--summary-output",
            str(summary_path),
            "--continue-on-error",
        ]
    )

    assert exit_code == 0
    assert success_output_path.exists()
    assert summary_path.exists()

    summary_frame = pd.read_csv(summary_path)

    assert len(summary_frame) == 2
    assert summary_frame.iloc[0]["status"] == "success"
    assert summary_frame.iloc[0]["row_count"] == 7
    assert summary_frame.iloc[1]["status"] == "failed"
    assert summary_frame.iloc[1]["row_count"] == 0
    assert "does not exist" in str(summary_frame.iloc[1]["error_message"])


def test_offline_batch_scan_cli_accepts_manifest_paths_exactly_as_provided_when_cwd_resolves_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "offline_batch_scan_sample.csv"
    manifest_path = tmp_path / "offline_scan_manifest.csv"
    monkeypatch.chdir(REPO_ROOT)
    pd.DataFrame(
        [
            {
                "input_path": "tests/fixtures/sample_option_chain.csv",
                "output_path": str(output_path),
                "as_of": "2026-01-02",
            }
        ]
    ).to_csv(manifest_path, index=False)

    exit_code = main(["--manifest", str(manifest_path)])

    assert exit_code == 0
    assert output_path.exists()

    output_frame = pd.read_csv(output_path)
    assert list(output_frame.columns) == SCANNER_OUTPUT_COLUMNS
    assert len(output_frame) == 7


def test_offline_batch_scan_cli_does_not_resolve_input_paths_relative_to_manifest_location(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifest_dir"
    manifest_dir.mkdir()
    copied_fixture = manifest_dir / "sample_option_chain.csv"
    copied_fixture.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    manifest_path = manifest_dir / "offline_scan_manifest.csv"
    pd.DataFrame(
        [
            {
                "input_path": "sample_option_chain.csv",
                "output_path": str(tmp_path / "unused.csv"),
                "as_of": "2026-01-02",
            }
        ]
    ).to_csv(manifest_path, index=False)

    with pytest.raises(FileNotFoundError, match="Manifest row 1 input file does not exist: sample_option_chain.csv"):
        main(["--manifest", str(manifest_path)])


def test_offline_batch_scan_cli_help_includes_expected_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["--help"])

    captured = capsys.readouterr()

    assert "research-only deterministic scanner" in captured.out
    assert "--manifest" in captured.out
    assert "--summary-output" in captured.out
    assert "--continue-on-error" in captured.out
