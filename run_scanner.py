"""Command-line workflow for running a simple options spread scanner.

Workflow:
- Load tickers ["SPY", "QQQ"]
- Load option chains
- Generate spreads
- Estimate probability
- Calculate EV
- Rank spreads

Output:
- print results
- save CSV
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import erf, log, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from options_edge_scanner.data.option_chain_loader import load_option_chain


TICKERS = ["SPY", "QQQ"]
OUTPUT_DIR = Path("outputs")
TOP_N = 40
MAX_STRIKE_GAP_RATIO = 0.10  # max spread width as % of underlying price
MIN_DTE_DAYS = 7
MAX_DTE_DAYS = 90


def _norm_cdf(x: float) -> float:
    """Fast standard normal CDF."""
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _probability_of_profit(
    *,
    underlying_price: float,
    short_strike: float,
    iv: float,
    years_to_expiry: float,
    spread_type: str,
) -> float:
    """Estimate probability that spread expires at max-profit condition.

    Uses a lognormal terminal-price assumption:
      ln(S_T / S_0) ~ N(-0.5 * sigma^2 * T, sigma * sqrt(T))
    """
    if (
        not np.isfinite(underlying_price)
        or not np.isfinite(short_strike)
        or not np.isfinite(iv)
        or underlying_price <= 0
        or short_strike <= 0
        or iv <= 0
        or years_to_expiry <= 0
    ):
        return float("nan")

    mu = -0.5 * (iv**2) * years_to_expiry
    sigma_t = iv * sqrt(years_to_expiry)
    z = (log(short_strike / underlying_price) - mu) / sigma_t

    if spread_type == "put_credit":
        # Profit when underlying ends above short strike.
        probability = 1.0 - _norm_cdf(z)
    else:
        # call_credit: profit when underlying ends below short strike.
        probability = _norm_cdf(z)

    return float(np.clip(probability, 0.0, 1.0))


def _generate_credit_spreads(chain: pd.DataFrame) -> pd.DataFrame:
    """Create call/put credit spreads and estimate probability + EV."""
    if chain.empty:
        return pd.DataFrame()

    now = datetime.now(timezone.utc)
    results: list[dict[str, float | str | datetime]] = []

    chain = chain.copy()
    chain["expiration"] = pd.to_datetime(chain["expiration"], utc=True, errors="coerce")

    for (ticker, expiration), exp_frame in chain.groupby(["ticker", "expiration"], sort=True):
        if pd.isna(expiration):
            continue

        dte_days = float((expiration.date() - now.date()).days)
        if dte_days < MIN_DTE_DAYS or dte_days > MAX_DTE_DAYS:
            continue

        years_to_expiry = dte_days / 365.25

        for option_type in ("put", "call"):
            side = exp_frame[exp_frame["type"] == option_type].copy()
            if side.empty:
                continue

            side = side.dropna(subset=["strike", "mid", "underlying_price", "implied_vol"])
            side = side[side["mid"] > 0]
            side = side.sort_values("strike")
            if len(side) < 2:
                continue

            underlying_price = float(pd.to_numeric(side["underlying_price"], errors="coerce").median())
            if not np.isfinite(underlying_price) or underlying_price <= 0:
                continue

            max_width = underlying_price * MAX_STRIKE_GAP_RATIO
            rows = side[["strike", "mid", "implied_vol"]].to_dict("records")

            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    lower = rows[i]
                    higher = rows[j]
                    width = float(higher["strike"] - lower["strike"])
                    if width <= 0 or width > max_width:
                        continue

                    if option_type == "put":
                        # Bull put credit: short higher strike, long lower strike.
                        short_leg = higher
                        long_leg = lower
                        spread_type = "put_credit"
                    else:
                        # Bear call credit: short lower strike, long higher strike.
                        short_leg = lower
                        long_leg = higher
                        spread_type = "call_credit"

                    credit = float(short_leg["mid"] - long_leg["mid"])
                    if credit <= 0:
                        continue

                    max_loss = width - credit
                    if max_loss <= 0:
                        continue

                    iv = float(np.nanmean([short_leg["implied_vol"], long_leg["implied_vol"]]))
                    pop = _probability_of_profit(
                        underlying_price=underlying_price,
                        short_strike=float(short_leg["strike"]),
                        iv=iv,
                        years_to_expiry=years_to_expiry,
                        spread_type=spread_type,
                    )
                    if not np.isfinite(pop):
                        continue

                    ev = pop * credit - (1.0 - pop) * max_loss

                    results.append(
                        {
                            "ticker": ticker,
                            "expiration": expiration.tz_convert(None),
                            "dte_days": round(dte_days, 1),
                            "spread_type": spread_type,
                            "short_strike": float(short_leg["strike"]),
                            "long_strike": float(long_leg["strike"]),
                            "width": width,
                            "credit": credit,
                            "max_loss": max_loss,
                            "implied_vol": iv,
                            "probability_of_profit": pop,
                            "expected_value": ev,
                            "ev_to_risk": ev / max_loss,
                        }
                    )

    if not results:
        return pd.DataFrame()

    spreads = pd.DataFrame(results)
    spreads = spreads.sort_values(
        by=["expected_value", "ev_to_risk", "probability_of_profit"],
        ascending=False,
    ).reset_index(drop=True)
    return spreads


def main() -> None:
    """Run the scanner workflow and output ranked spread candidates."""
    print(f"Running options spread scanner for tickers: {TICKERS}")

    chains: list[pd.DataFrame] = []
    for ticker in TICKERS:
        print(f"Loading option chain for {ticker}...")
        try:
            chain = load_option_chain(ticker)
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            print(f"  Failed to load {ticker}: {exc}")
            continue

        if chain.empty:
            print(f"  No option data found for {ticker}.")
            continue
        chains.append(chain)

    if not chains:
        print("No option chains loaded; exiting.")
        return

    combined = pd.concat(chains, ignore_index=True)
    spreads = _generate_credit_spreads(combined)

    if spreads.empty:
        print("No candidate spreads generated with current filters.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"spread_scan_results_{timestamp}.csv"

    spreads.to_csv(output_path, index=False)

    printable = spreads.head(TOP_N).copy()
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 180)
    pd.set_option("display.float_format", lambda x: f"{x:,.4f}")

    print("\nTop ranked spreads:")
    print(printable)
    print(f"\nSaved {len(spreads)} spreads to: {output_path}")


if __name__ == "__main__":
    main()
