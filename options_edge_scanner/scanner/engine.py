"""Orchestration entrypoint for scanning workflow."""

from options_edge_scanner.config import ScannerConfig



def run_scan(config: ScannerConfig) -> None:
    """Run the end-to-end options edge scanning process."""
    # TODO: Wire data loading, modeling, signal generation, and reporting.
    _ = config
