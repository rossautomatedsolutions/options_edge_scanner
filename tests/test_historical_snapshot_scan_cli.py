from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pytest

from options_edge_scanner.cli.historical_snapshot_scan import SUMMARY_OUTPUT_COLUMNS, main
from options_edge_scanner.data.historical_snapshot_loader import load_historical_snapshots
from options_edge_scanner.scanner.engine import SCANNER_OUTPUT_COLUMNS


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def _load_fixture_quotes() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_PATH)


def _write_snapshot(
    root: Path,
    snapshot_id: str,
    *,
    quote_observed_at: str,
    ticker: str = "XYZ",
    underlying_price: float = 100.0,
    underlying_price_observed_at: str | None = None,
    underlying_price_source: str = "fixture.snapshot",
    chain_mutator: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    drop_chain_columns: list[str] | None = None,
    metadata_overrides: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    snapshot_dir = root / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    quote_frame = _load_fixture_quotes().copy()
    quote_frame["ticker"] = ticker
    quote_frame["quote_observed_at"] = quote_observed_at
    quote_frame["underlying_price"] = underlying_price
    quote_frame["underlying_price_observed_at"] = (
        underlying_price_observed_at or quote_observed_at
    )
    quote_frame["underlying_price_source"] = underlying_price_source
    if chain_mutator is not None:
        quote_frame = chain_mutator(quote_frame.copy())
    if drop_chain_columns:
        quote_frame = quote_frame.drop(columns=drop_chain_columns)

    chain_path = snapshot_dir / f"{snapshot_id}.csv"
    quote_frame.to_csv(chain_path, index=False)

    expirations = pd.to_datetime(quote_frame.get("expiration"), errors="coerce").dropna()
    expiration_start = (
        expirations.min().normalize().strftime("%Y-%m-%d") if not expirations.empty else "2026-02-13"
    )
    expiration_end = (
        expirations.max().normalize().strftime("%Y-%m-%d") if not expirations.empty else "2026-02-13"
    )
    metadata = {
        "snapshot_id": snapshot_id,
        "snapshot_source": "fixture.vendor",
        "source_vendor": "fixture.vendor",
        "ticker_normalized": ticker,
        "quote_observed_at": quote_observed_at,
        "underlying_price": underlying_price,
        "underlying_price_observed_at": underlying_price_observed_at or quote_observed_at,
        "underlying_price_source": underlying_price_source,
        "expiration_start": expiration_start,
        "expiration_end": expiration_end,
    }
    metadata.update(metadata_overrides or {})

    metadata_path = chain_path.with_suffix(chain_path.suffix + ".meta.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return chain_path, metadata_path


def _manifest_row(
    manifest_dir: Path,
    *,
    snapshot_id: str,
    as_of: str,
    chain_path: Path,
    metadata_path: Path,
    ticker: str = "XYZ",
    use_relative_paths: bool = True,
    **extra_fields: Any,
) -> dict[str, Any]:
    def _path_ref(path: Path) -> str:
        if not use_relative_paths:
            return str(path)
        return Path(os.path.relpath(path, manifest_dir)).as_posix()

    row = {
        "snapshot_id": snapshot_id,
        "ticker": ticker,
        "as_of": as_of,
        "chain_path": _path_ref(chain_path),
        "metadata_path": _path_ref(metadata_path),
    }
    row.update(extra_fields)
    return row


def _write_manifest(manifest_path: Path, rows: list[dict[str, Any]]) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(manifest_path, index=False)
    return manifest_path


def test_historical_snapshot_scan_cli_writes_deterministic_combined_output(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path_a, metadata_path_a = _write_snapshot(
        manifest_dir,
        "xyz-20260102-153000",
        quote_observed_at="2026-01-02T15:30:00Z",
        underlying_price=100.0,
    )
    chain_path_b, metadata_path_b = _write_snapshot(
        manifest_dir,
        "xyz-20260102-154500",
        quote_observed_at="2026-01-02T15:45:00Z",
        underlying_price=101.0,
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-20260102-153000",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_a,
                metadata_path=metadata_path_a,
            ),
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-20260102-154500",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_b,
                metadata_path=metadata_path_b,
            ),
        ],
    )
    output_path = tmp_path / "combined_candidates.csv"
    summary_path = tmp_path / "combined_summary.csv"
    repeat_output_path = tmp_path / "combined_candidates_repeat.csv"

    first_exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    )
    second_exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(repeat_output_path),
        ]
    )

    assert first_exit_code == 0
    assert second_exit_code == 0
    output_frame = pd.read_csv(output_path)
    repeat_output_frame = pd.read_csv(repeat_output_path)
    summary_frame = pd.read_csv(summary_path)

    assert list(output_frame.columns) == SCANNER_OUTPUT_COLUMNS
    assert output_frame.equals(repeat_output_frame)
    assert len(output_frame) == 10
    assert list(summary_frame.columns) == list(SUMMARY_OUTPUT_COLUMNS)
    assert summary_frame["status"].tolist() == ["success", "success"]
    assert summary_frame["row_count"].tolist() == [4, 6]
    assert output_frame["snapshot_id"].tolist()[:4] == ["xyz-20260102-153000"] * 4
    assert output_frame["snapshot_id"].tolist()[4:] == ["xyz-20260102-154500"] * 6
    assert set(output_frame["snapshot_source"]) == {"fixture.vendor"}
    assert set(output_frame["input_path"]) == {
        "snapshots/xyz-20260102-153000.csv",
        "snapshots/xyz-20260102-154500.csv",
    }
    assert set(output_frame["source_metadata_path"]) == {
        "snapshots/xyz-20260102-153000.csv.meta.json",
        "snapshots/xyz-20260102-154500.csv.meta.json",
    }
    assert output_frame["quote_observed_at"].iloc[0] == "2026-01-02 15:30:00"
    assert output_frame["quote_observed_at"].iloc[-1] == "2026-01-02 15:45:00"
    assert output_frame["expected_value"].iloc[:4].is_monotonic_decreasing
    assert output_frame["expected_value"].iloc[4:].is_monotonic_decreasing


def test_load_historical_snapshots_resolves_manifest_relative_paths(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "nested" / "manifests"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-relative",
        quote_observed_at="2026-01-02T15:30:00Z",
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-relative",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    snapshots = load_historical_snapshots(manifest_path)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.chain_path == chain_path.resolve(strict=False)
    assert snapshot.metadata_path == metadata_path.resolve(strict=False)
    assert snapshot.chain_path_ref == "snapshots/xyz-relative.csv"
    assert snapshot.metadata_path_ref == "snapshots/xyz-relative.csv.meta.json"
    assert set(snapshot.option_quotes["input_path"]) == {"snapshots/xyz-relative.csv"}
    assert set(snapshot.option_quotes["source_metadata_path"]) == {
        "snapshots/xyz-relative.csv.meta.json"
    }


def test_load_historical_snapshots_rejects_chain_metadata_timestamp_mismatch(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-mismatch",
        quote_observed_at="2026-01-02T15:30:00Z",
        metadata_overrides={"quote_observed_at": "2026-01-02T15:45:00Z"},
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-mismatch",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="quote_observed_at"):
        load_historical_snapshots(manifest_path)


def test_load_historical_snapshots_rejects_stale_spot_metadata(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-stale-spot",
        quote_observed_at="2026-01-02T15:30:00Z",
        metadata_overrides={"underlying_price_observed_at": "2026-01-02T14:30:00Z"},
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-stale-spot",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="must use the same timestamp"):
        load_historical_snapshots(manifest_path)


def test_historical_snapshot_scan_cli_marks_duplicate_snapshot_ids_failed(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path_a, metadata_path_a = _write_snapshot(
        manifest_dir,
        "dup-a",
        quote_observed_at="2026-01-02T15:30:00Z",
    )
    chain_path_b, metadata_path_b = _write_snapshot(
        manifest_dir,
        "dup-b",
        quote_observed_at="2026-01-02T15:45:00Z",
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="dup-id",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_a,
                metadata_path=metadata_path_a,
            ),
            _manifest_row(
                manifest_dir,
                snapshot_id="dup-id",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_b,
                metadata_path=metadata_path_b,
            ),
        ],
    )
    output_path = tmp_path / "duplicate_candidates.csv"
    summary_path = tmp_path / "duplicate_summary.csv"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    output_frame = pd.read_csv(output_path)
    summary_frame = pd.read_csv(summary_path)
    assert exit_code == 1
    assert output_frame.empty
    assert summary_frame["status"].tolist() == ["failed", "failed"]
    assert summary_frame["error_message"].str.contains("reuse the same snapshot_id").all()


def test_historical_snapshot_scan_cli_rejects_duplicate_metadata_path_reuse(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path_a, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-meta-a",
        quote_observed_at="2026-01-02T15:30:00Z",
    )
    chain_path_b, _ = _write_snapshot(
        manifest_dir,
        "xyz-meta-b",
        quote_observed_at="2026-01-02T15:45:00Z",
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-meta-a",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_a,
                metadata_path=metadata_path,
            ),
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-meta-b",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_b,
                metadata_path=metadata_path,
            ),
        ],
    )
    output_path = tmp_path / "duplicate_metadata_candidates.csv"
    summary_path = tmp_path / "duplicate_metadata_summary.csv"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    summary_frame = pd.read_csv(summary_path)
    assert exit_code == 1
    assert summary_frame["status"].tolist() == ["failed", "failed"]
    assert summary_frame["error_message"].str.contains(
        "resolve metadata_path to the same local artifact"
    ).all()


def test_load_historical_snapshots_rejects_bad_symbol_mismatch(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-bad-symbol",
        quote_observed_at="2026-01-02T15:30:00Z",
        chain_mutator=lambda frame: frame.assign(ticker="ABC"),
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-bad-symbol",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="does not match manifest ticker"):
        load_historical_snapshots(manifest_path)


def test_load_historical_snapshots_rejects_metadata_snapshot_id_mismatch(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-manifest-id",
        quote_observed_at="2026-01-02T15:30:00Z",
        metadata_overrides={"snapshot_id": "xyz-sidecar-id"},
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-manifest-id",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="metadata snapshot_id"):
        load_historical_snapshots(manifest_path)


def test_load_historical_snapshots_require_metadata_snapshot_id(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-no-sidecar-id",
        quote_observed_at="2026-01-02T15:30:00Z",
        metadata_overrides={"snapshot_id": None},
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-no-sidecar-id",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="metadata must include snapshot_id"):
        load_historical_snapshots(manifest_path)


def test_load_historical_snapshots_rejects_chain_snapshot_id_mismatch(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-manifest-id",
        quote_observed_at="2026-01-02T15:30:00Z",
        chain_mutator=lambda frame: frame.assign(snapshot_id="xyz-chain-id"),
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-manifest-id",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="chain snapshot_id"):
        load_historical_snapshots(manifest_path)


def test_historical_snapshot_scan_cli_preserves_valid_invalid_and_zero_candidate_rows(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path_valid, metadata_path_valid = _write_snapshot(
        manifest_dir,
        "xyz-valid",
        quote_observed_at="2026-01-02T15:30:00Z",
    )
    chain_path_zero, metadata_path_zero = _write_snapshot(
        manifest_dir,
        "xyz-zero",
        quote_observed_at="2026-01-02T15:45:00Z",
        chain_mutator=lambda frame: frame.loc[frame["strike"] == 95.0].reset_index(drop=True),
    )
    missing_chain_path = manifest_dir / "snapshots" / "missing.csv"
    missing_metadata_path = manifest_dir / "snapshots" / "missing.csv.meta.json"
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-valid",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_valid,
                metadata_path=metadata_path_valid,
            ),
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-missing",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=missing_chain_path,
                metadata_path=missing_metadata_path,
            ),
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-zero",
                ticker="XYZ",
                as_of="2026-01-02",
                chain_path=chain_path_zero,
                metadata_path=metadata_path_zero,
            ),
        ],
    )
    output_path = tmp_path / "mixed_candidates.csv"
    summary_path = tmp_path / "mixed_summary.csv"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    output_frame = pd.read_csv(output_path)
    summary_frame = pd.read_csv(summary_path)
    assert exit_code == 1
    assert len(output_frame) == 4
    assert summary_frame["snapshot_id"].tolist() == ["xyz-valid", "xyz-missing", "xyz-zero"]
    assert summary_frame["status"].tolist() == ["success", "failed", "success"]
    assert summary_frame["row_count"].tolist() == [4, 0, 0]
    assert "chain file does not exist" in str(summary_frame.iloc[1]["error_message"])


def test_historical_snapshot_scan_cli_records_malformed_timestamp_failure(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-bad-asof",
        quote_observed_at="2026-01-02T15:30:00Z",
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-bad-asof",
                ticker="XYZ",
                as_of="not-a-date",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )
    output_path = tmp_path / "bad_asof_candidates.csv"
    summary_path = tmp_path / "bad_asof_summary.csv"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    output_frame = pd.read_csv(output_path)
    summary_frame = pd.read_csv(summary_path)
    assert exit_code == 1
    assert output_frame.empty
    assert summary_frame.iloc[0]["status"] == "failed"
    assert "invalid as_of" in str(summary_frame.iloc[0]["error_message"])


def test_historical_snapshot_scan_cli_records_manifest_schema_failure(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad_manifest.csv"
    pd.DataFrame(
        [
            {
                "snapshot_id": "xyz-bad-schema",
                "ticker": "XYZ",
                "chain_path": "missing.csv",
                "metadata_path": "missing.csv.meta.json",
            }
        ]
    ).to_csv(manifest_path, index=False)
    output_path = tmp_path / "bad_schema_candidates.csv"
    summary_path = tmp_path / "bad_schema_summary.csv"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
        ]
    )

    summary_frame = pd.read_csv(summary_path)
    assert exit_code == 1
    assert summary_frame.iloc[0]["status"] == "failed"
    assert "Missing required historical snapshot manifest columns: as_of" in str(
        summary_frame.iloc[0]["error_message"]
    )


def test_load_historical_snapshots_rejects_lookahead_as_of(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifest"
    chain_path, metadata_path = _write_snapshot(
        manifest_dir,
        "xyz-lookahead",
        quote_observed_at="2026-01-02T15:30:00Z",
    )
    manifest_path = _write_manifest(
        manifest_dir / "historical_manifest.csv",
        [
            _manifest_row(
                manifest_dir,
                snapshot_id="xyz-lookahead",
                ticker="XYZ",
                as_of="2026-01-01",
                chain_path=chain_path,
                metadata_path=metadata_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="predates the observed option snapshot timestamp"):
        load_historical_snapshots(manifest_path)
