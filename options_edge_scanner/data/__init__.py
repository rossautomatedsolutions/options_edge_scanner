"""Data access layer for market and options datasets."""

from .option_chain_loader import load_option_chain

__all__ = ["load_option_chain"]
