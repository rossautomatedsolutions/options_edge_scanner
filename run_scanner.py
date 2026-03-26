"""Command-line entrypoint for running the options edge scanner."""

from options_edge_scanner.config import get_default_config
from options_edge_scanner.scanner.engine import run_scan



def main() -> None:
    """Load configuration and invoke the scanner pipeline."""
    # TODO: Add argument parsing and runtime wiring.
    config = get_default_config()
    run_scan(config)


if __name__ == "__main__":
    main()
