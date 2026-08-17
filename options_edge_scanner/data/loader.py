"""Offline local-file adapter for canonical option quote inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from options_edge_scanner.data.provenance import normalize_provenance_columns


OPTION_QUOTE_REQUIRED_COLUMNS = (
    "ticker",
    "expiration",
    "strike",
    "type",
    "bid",
    "ask",
    "implied_vol",
    "underlying_price",
)

_SAFE_COLUMN_ALIASES = {
    "option_type": "type",
    "expiry": "expiration",
    "expiry_date": "expiration",
    "expiration_date": "expiration",
    "strike_price": "strike",
    "iv": "implied_vol",
    "implied_volatility": "implied_vol",
}


def _normalize_columns(columns: Iterable[str]) -> dict[str, str]:
    """Return safe column renames keyed by original column name."""
    normalized_lookup = {str(column).strip().lower(): column for column in columns}
    renames: dict[str, str] = {}
    for alias, canonical in _SAFE_COLUMN_ALIASES.items():
        source = normalized_lookup.get(alias)
        if source is not None and canonical not in columns:
            renames[source] = canonical
    return renames


def _read_local_frame(path: Path) -> pd.DataFrame:
    """Read a local CSV or parquet file into a dataframe."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        try:
            return pd.read_parquet(path)
        except ImportError as exc:
            raise ImportError(
                "Parquet support requires pandas parquet dependencies such as pyarrow or fastparquet"
            ) from exc
    raise ValueError(f"Unsupported file type: {path.suffix or '<no extension>'}")


def validate_option_quote_frame(
    option_quotes: pd.DataFrame,
    *,
    require_underlying_price: bool = True,
) -> pd.DataFrame:
    """Validate and normalize a dataframe against the OptionQuoteRow contract."""
    working = option_quotes.copy()
    renames = _normalize_columns(working.columns)
    if renames:
        working = working.rename(columns=renames)

    required_columns = [
        column
        for column in OPTION_QUOTE_REQUIRED_COLUMNS
        if require_underlying_price or column != "underlying_price"
    ]
    missing_columns = [column for column in required_columns if column not in working.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required OptionQuoteRow columns: {missing}")

    if "underlying_price" not in working.columns:
        working["underlying_price"] = pd.NA

    working["expiration"] = pd.to_datetime(working["expiration"], errors="coerce")
    working["ticker"] = working["ticker"].astype("string").str.upper()
    working["type"] = (
        working["type"].astype("string").str.strip().str.lower().replace({"c": "call", "p": "put"})
    )

    for column in ("strike", "bid", "ask", "implied_vol", "underlying_price"):
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if "mid" in working.columns:
        working["mid"] = pd.to_numeric(working["mid"], errors="coerce")
    else:
        working["mid"] = pd.NA

    derived_mid = (working["bid"] + working["ask"]) / 2.0
    working.loc[working["mid"].isna(), "mid"] = derived_mid.loc[working["mid"].isna()]

    working = normalize_provenance_columns(working)
    return working.reset_index(drop=True)


def load_option_quotes(
    path: str | Path,
    *,
    require_underlying_price: bool = True,
) -> pd.DataFrame:
    """Load contract-compliant option quotes from a local CSV or parquet file."""
    file_path = Path(path)
    option_quotes = _read_local_frame(file_path)
    return validate_option_quote_frame(
        option_quotes,
        require_underlying_price=require_underlying_price,
    )
