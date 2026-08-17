"""Data access layer for market and options datasets."""

from .alpaca_historical import (
    AlpacaAcquisitionError,
    AlpacaCredentials,
    AlpacaRealizedUnderlyingAcquisition,
    AlpacaStockBarsRequest,
    acquire_alpaca_realized_underlying,
    fetch_alpaca_stock_bars_pages,
    load_alpaca_credentials_from_env,
    normalize_alpaca_stock_bars_to_realized_underlying,
)
from .historical_snapshot_loader import (
    HistoricalSnapshot,
    HistoricalSnapshotSpec,
    load_historical_snapshot,
    load_historical_snapshot_manifest_frame,
    load_historical_snapshots,
    parse_historical_snapshot_manifest,
    validate_historical_snapshot_manifest_row,
)
from .loader import load_option_quotes, validate_option_quote_frame
from .option_chain_loader import load_option_chain
from .realized_underlying import (
    REALIZED_UNDERLYING_OPTIONAL_COLUMNS,
    REALIZED_UNDERLYING_REQUIRED_COLUMNS,
    build_realized_underlying_artifact_id,
    build_realized_underlying_observation_id,
    load_realized_underlying_artifacts,
    load_realized_underlying_frame,
    validate_realized_underlying_frame,
    write_realized_underlying_frame,
)

__all__ = [
    "AlpacaAcquisitionError",
    "AlpacaCredentials",
    "AlpacaRealizedUnderlyingAcquisition",
    "AlpacaStockBarsRequest",
    "HistoricalSnapshot",
    "HistoricalSnapshotSpec",
    "REALIZED_UNDERLYING_OPTIONAL_COLUMNS",
    "REALIZED_UNDERLYING_REQUIRED_COLUMNS",
    "acquire_alpaca_realized_underlying",
    "build_realized_underlying_artifact_id",
    "build_realized_underlying_observation_id",
    "fetch_alpaca_stock_bars_pages",
    "load_alpaca_credentials_from_env",
    "load_historical_snapshot",
    "load_historical_snapshot_manifest_frame",
    "load_historical_snapshots",
    "load_option_chain",
    "load_option_quotes",
    "load_realized_underlying_artifacts",
    "load_realized_underlying_frame",
    "normalize_alpaca_stock_bars_to_realized_underlying",
    "parse_historical_snapshot_manifest",
    "validate_historical_snapshot_manifest_row",
    "validate_option_quote_frame",
    "validate_realized_underlying_frame",
    "write_realized_underlying_frame",
]
