from __future__ import annotations

import run_scanner


def test_run_scanner_reports_retired_workflow(capsys) -> None:
    exit_code = run_scanner.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "retired" in captured.out
    assert "offline_scan" in captured.out
