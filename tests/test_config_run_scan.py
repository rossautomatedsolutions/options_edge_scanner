from __future__ import annotations

import json
from pathlib import Path

from options_edge_scanner.config import ScannerConfig
from options_edge_scanner.scanner.engine import run_scan


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def test_configured_run_scan_returns_ranked_opportunities_and_report(tmp_path: Path) -> None:
    """The documented config API must work from a normal package import path."""
    output_path = tmp_path / "ranked_opportunities.csv"
    report_path = tmp_path / "scan_report.json"

    opportunities = run_scan(
        ScannerConfig(
            input_path=FIXTURE_PATH,
            output_path=output_path,
            report_output_path=report_path,
            as_of="2026-01-02",
        )
    )

    assert output_path.exists()
    assert report_path.exists()
    assert len(opportunities) == 4
    assert opportunities.iloc[0]["selection_rank"] == 1
    assert opportunities.iloc[0]["spread_type"] == "bear_put_debit"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "run_scan_config"
    assert report["counts"]["prepared_quote_count"] == 8
    assert report["counts"]["ranked_candidate_count"] == 4
