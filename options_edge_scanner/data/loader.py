"""Placeholder data loader interfaces."""

import pandas as pd



def fetch_price_history(symbol: str) -> pd.DataFrame:
    """Fetch historical prices for a symbol."""
    # TODO: Implement data retrieval using yfinance and caching.
    return pd.DataFrame()



def fetch_options_chain(symbol: str) -> pd.DataFrame:
    """Fetch options chain data for a symbol."""
    # TODO: Implement options chain retrieval and normalization.
    return pd.DataFrame()
