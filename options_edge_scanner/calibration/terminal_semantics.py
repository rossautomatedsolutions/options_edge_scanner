"""Explicit terminal-price observation semantics for realized outcome research."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
)

from options_edge_scanner.calibration.contracts import (
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    format_date_like,
    format_utc_timestamp,
)


_NEW_YORK_TZ = ZoneInfo("America/New_York")


class _USEquityMarketHolidayCalendar(AbstractHolidayCalendar):
    """Approximate regular US equity market holidays needed for contract validation."""

    rules = [
        Holiday("NewYearsDay", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday, start_date="2022-06-19"),
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("ChristmasDay", month=12, day=25, observance=nearest_workday),
    ]


_US_EQUITY_MARKET_HOLIDAYS = _USEquityMarketHolidayCalendar()


@dataclass(frozen=True)
class TerminalObservationPolicy:
    """Explicit policy defining one terminal underlying observation convention."""

    ticker: str
    required_outcome_horizon: str
    terminal_price_convention: str
    terminal_price_convention_version: str
    realized_outcome_measure: str
    price_field: str
    observed_market_session: str
    market_timezone: str
    market_close_hour: int
    market_close_minute: int
    policy_scope: str
    settlement_summary: str
    research_proxy_summary: str

    def to_metadata(self) -> dict[str, object]:
        """Return one JSON-serializable metadata dictionary."""
        return asdict(self)


SPY_EXPIRATION_CLOSE_POLICY = TerminalObservationPolicy(
    ticker="SPY",
    required_outcome_horizon="expiration",
    terminal_price_convention="spy_expiration_day_close_proxy",
    terminal_price_convention_version="1",
    realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    price_field="close",
    observed_market_session="regular_close",
    market_timezone="America/New_York",
    market_close_hour=16,
    market_close_minute=0,
    policy_scope="SPY ETF options only",
    settlement_summary=(
        "SPY ETF options are American-style, physically settled, and PM-settled; "
        "the expiration event resolves against the expiration-date underlying close."
    ),
    research_proxy_summary=(
        "Use the expiration-date SPY 4:00 p.m. America/New_York close timestamp together "
        "with a provider-sourced end-of-day close proxy. This is appropriate for close-based "
        "expiration event research but does not claim the provider field is the official "
        "closing-auction print, and it does not model contrary exercise instructions, "
        "assignment choice, or post-close share exposure."
    ),
)


def resolve_terminal_observation_policy(
    *,
    ticker: str,
    required_outcome_horizon: str,
) -> TerminalObservationPolicy:
    """Return the explicit supported terminal observation policy for one ticker/horizon."""
    normalized_ticker = str(ticker).strip().upper()
    normalized_horizon = str(required_outcome_horizon).strip()

    if normalized_ticker == "SPY" and normalized_horizon == "expiration":
        return SPY_EXPIRATION_CLOSE_POLICY

    raise ValueError(
        "No explicit terminal observation policy is defined for "
        f"ticker={normalized_ticker}, required_outcome_horizon={normalized_horizon}. "
        "Add a new symbol-specific policy instead of silently reusing the SPY convention."
    )


def market_close_timestamp_for_event_date(
    event_date: object,
    *,
    policy: TerminalObservationPolicy,
) -> str:
    """Return the explicit UTC timestamp for one policy's market close."""
    normalized_date = pd.to_datetime(event_date, errors="coerce")
    if pd.isna(normalized_date):
        raise ValueError(f"Invalid event_date: {event_date}")

    date_value = pd.Timestamp(normalized_date).date()
    if not is_us_equity_trading_day(date_value):
        raise ValueError(
            f"event_date {date_value.isoformat()} is not a regular US equity trading day."
        )
    local_timestamp = datetime.combine(
        date_value,
        time(hour=policy.market_close_hour, minute=policy.market_close_minute),
        tzinfo=_NEW_YORK_TZ,
    )
    return format_utc_timestamp(local_timestamp.astimezone(ZoneInfo("UTC")))


def normalize_event_date_for_policy(event_date: object) -> str:
    """Return one policy-normalized event date string."""
    return format_date_like(event_date)


def is_us_equity_trading_day(event_date: object) -> bool:
    """Return whether one date is a regular US equity trading day."""
    normalized = pd.to_datetime(event_date, errors="coerce")
    if pd.isna(normalized):
        return False

    timestamp = pd.Timestamp(normalized).normalize()
    if timestamp.weekday() >= 5:
        return False

    holidays = _US_EQUITY_MARKET_HOLIDAYS.holidays(start=timestamp, end=timestamp)
    return timestamp not in set(holidays)
