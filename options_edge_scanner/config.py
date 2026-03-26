"""Configuration settings for the options edge scanner project."""

from dataclasses import dataclass


@dataclass
class ScannerConfig:
    """Container for scanner configuration parameters."""

    symbol_universe: list[str]
    lookback_days: int
    risk_free_rate: float



def get_default_config() -> ScannerConfig:
    """Return default project configuration values."""
    # TODO: Replace placeholder defaults with environment-driven configuration.
    return ScannerConfig(symbol_universe=[], lookback_days=30, risk_free_rate=0.0)
