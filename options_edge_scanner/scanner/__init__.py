"""Scanner orchestration package.

The public convenience exports are resolved lazily so importing
``ScannerConfig`` does not load the orchestration module before the config
class is defined.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_scanner_opportunities", "rank_spreads"]


def __getattr__(name: str) -> Any:
    """Resolve convenience exports without creating a config/engine cycle."""
    if name == "build_scanner_opportunities":
        from options_edge_scanner.scanner.engine import build_scanner_opportunities

        return build_scanner_opportunities
    if name == "rank_spreads":
        from options_edge_scanner.scanner.opportunity_ranker import rank_spreads

        return rank_spreads
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
