"""Configuration settings for the maintained offline scanner workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from options_edge_scanner.scanner.quality_filters import OfflineScanQualitySettings


@dataclass(frozen=True)
class ScannerConfig:
    """Configuration for one offline local-file scanner run."""

    input_path: str | Path = ""
    output_path: str | Path | None = None
    report_output_path: str | Path | None = None
    as_of: str | None = None
    spot: float | None = None
    spot_observed_at: str | None = None
    spot_source: str | None = None
    allow_unsafe_as_of: bool = False
    quality_settings: OfflineScanQualitySettings = field(default_factory=OfflineScanQualitySettings)


def get_default_config() -> ScannerConfig:
    """Return default project configuration values."""
    return ScannerConfig()
