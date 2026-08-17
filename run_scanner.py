"""Retired legacy entrypoint kept only to redirect callers to the offline flow."""

from __future__ import annotations

MIGRATION_MESSAGE = """\
run_scanner.py has been retired.

Why:
- it used a separate live-data prototype that bypassed the current offline scanner contracts
- it did not enforce point-in-time provenance checks
- it used a different spread/EV stack than the maintained offline workflow

Use this flow instead:
1. `python -m options_edge_scanner.cli.yahoo_option_chain_ingest --ticker SPY --expiration nearest --output-dir outputs/yahoo_option_chains/SPY`
2. `python -m options_edge_scanner.cli.offline_scan --input outputs/yahoo_option_chains/SPY/SPY_YYYY-MM-DD_yahoo.csv --output outputs/offline_scan_spy.csv --as-of YYYY-MM-DD`
"""


def main() -> int:
    """Explain how to use the maintained offline scanner workflow."""
    print(MIGRATION_MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
