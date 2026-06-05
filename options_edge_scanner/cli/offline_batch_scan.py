"""Research-only offline batch scan entrypoint for local quote manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from options_edge_scanner.cli.offline_scan import run_offline_scan


MANIFEST_REQUIRED_COLUMNS = ("input_path", "output_path", "as_of")
SUMMARY_OUTPUT_COLUMNS = ("input_path", "output_path", "as_of", "status", "row_count", "error_message")


def _load_manifest(manifest_path: str | Path) -> pd.DataFrame:
    """Load a batch manifest from local CSV or JSON."""
    path = Path(manifest_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        manifest = pd.read_csv(path)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        manifest = pd.DataFrame(payload)
    else:
        raise ValueError(f"Unsupported manifest file type: {path.suffix or '<no extension>'}")

    missing_columns = [column for column in MANIFEST_REQUIRED_COLUMNS if column not in manifest.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required manifest columns: {missing}")

    return manifest.loc[:, list(MANIFEST_REQUIRED_COLUMNS)].reset_index(drop=True)


def _validate_manifest_row(row: pd.Series, row_number: int) -> dict[str, str]:
    """Validate one manifest row and return normalized string paths/date."""
    input_path = str(row["input_path"]).strip()
    output_path = str(row["output_path"]).strip()
    as_of = str(row["as_of"]).strip()

    if not input_path:
        raise ValueError(f"Manifest row {row_number} has an empty input_path")
    if not output_path:
        raise ValueError(f"Manifest row {row_number} has an empty output_path")
    if not as_of:
        raise ValueError(f"Manifest row {row_number} has an empty as_of")

    parsed_as_of = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(parsed_as_of):
        raise ValueError(f"Manifest row {row_number} has invalid as_of date: {as_of}")

    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Manifest row {row_number} input file does not exist: {input_file}")

    return {
        "input_path": input_path,
        "output_path": output_path,
        "as_of": parsed_as_of.strftime("%Y-%m-%d"),
    }


def _write_summary(summary: pd.DataFrame, summary_output_path: str | Path | None) -> None:
    """Write the batch summary CSV if a destination is provided."""
    if summary_output_path is None:
        return

    output_file = Path(summary_output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_file, index=False)


def run_offline_batch_scan(
    manifest_path: str | Path,
    *,
    summary_output_path: str | Path | None = None,
    continue_on_error: bool = False,
) -> pd.DataFrame:
    """Run the deterministic offline scanner for each manifest row."""
    manifest = _load_manifest(manifest_path)
    summary_rows: list[dict[str, Any]] = []

    for idx, row in manifest.iterrows():
        row_number = idx + 1
        raw_input_path = str(row.get("input_path", "")).strip()
        raw_output_path = str(row.get("output_path", "")).strip()
        raw_as_of = str(row.get("as_of", "")).strip()

        try:
            validated = _validate_manifest_row(row, row_number=row_number)
            output_file = run_offline_scan(
                input_path=validated["input_path"],
                output_path=validated["output_path"],
                as_of=validated["as_of"],
            )
            output_frame = pd.read_csv(output_file)
            summary_rows.append(
                {
                    "input_path": validated["input_path"],
                    "output_path": str(output_file),
                    "as_of": validated["as_of"],
                    "status": "success",
                    "row_count": int(len(output_frame)),
                    "error_message": "",
                }
            )
        except Exception as exc:
            summary_rows.append(
                {
                    "input_path": raw_input_path,
                    "output_path": raw_output_path,
                    "as_of": raw_as_of,
                    "status": "failed",
                    "row_count": 0,
                    "error_message": str(exc),
                }
            )
            if not continue_on_error:
                summary = pd.DataFrame(summary_rows, columns=list(SUMMARY_OUTPUT_COLUMNS))
                _write_summary(summary, summary_output_path)
                raise

    summary = pd.DataFrame(summary_rows, columns=list(SUMMARY_OUTPUT_COLUMNS))
    _write_summary(summary, summary_output_path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the offline batch scan entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only deterministic scanner for each local quote file "
            "listed in a CSV or JSON manifest and write ranked CSV outputs."
        )
    )
    parser.add_argument("--manifest", required=True, help="Local CSV or JSON batch manifest path")
    parser.add_argument(
        "--summary-output",
        dest="summary_output",
        default=None,
        help="Optional CSV path for a batch summary artifact",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing later manifest rows after a row-level failure",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the offline batch scan."""
    args = build_parser().parse_args(argv)
    summary = run_offline_batch_scan(
        args.manifest,
        summary_output_path=args.summary_output,
        continue_on_error=args.continue_on_error,
    )

    print("Offline research-only batch scan complete. No live data was fetched.")
    for row in summary.to_dict("records"):
        print(
            f"{row['input_path']} -> {row['output_path']} "
            f"(as_of={row['as_of']}, status={row['status']}, "
            f"row_count={row['row_count']}, error_message={row['error_message']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
