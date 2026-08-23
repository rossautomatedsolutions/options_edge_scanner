"""Outcome materialization helpers for normalized realized underlying observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from options_edge_scanner.calibration.contracts import (
    OUTCOME_REQUIRED_COLUMNS,
    TERMINAL_UNDERLYING_OUTCOME_MEASURE,
    build_required_outcome_key,
    ensure_parent,
    format_date_like,
    format_utc_timestamp,
    validate_realized_outcome_frame,
)
from options_edge_scanner.calibration.terminal_semantics import (
    market_close_timestamp_for_event_date,
    resolve_terminal_observation_policy,
)
from options_edge_scanner.data.historical_snapshot_loader import load_historical_snapshots
from options_edge_scanner.data.realized_underlying import (
    load_realized_underlying_artifacts,
    validate_realized_underlying_frame,
)


REQUIRED_OUTCOME_REQUEST_COLUMNS = (
    "required_outcome_key",
    "ticker",
    "expiration",
    "required_outcome_horizon",
    "realized_outcome_measure",
    "terminal_price_convention",
    "terminal_price_convention_version",
    "source_snapshot_count",
    "source_snapshot_ids",
)


def _current_utc_timestamp() -> pd.Timestamp:
    """Return one timezone-naive UTC timestamp for internal cutoff bookkeeping."""
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


@dataclass(frozen=True)
class RequiredOutcomeRequestPartition:
    """Partition required outcomes into already-realized versus future-dated requests."""

    realized_as_of: pd.Timestamp
    eligible_required_observations: pd.DataFrame
    future_required_observations: pd.DataFrame


@dataclass(frozen=True)
class MaterializedRealizedOutcomeArtifacts:
    """Machine-readable outcome materialization outputs."""

    required_observations: pd.DataFrame
    outcomes: pd.DataFrame
    eligible_required_observations: pd.DataFrame = field(default_factory=pd.DataFrame)
    future_required_observations: pd.DataFrame = field(default_factory=pd.DataFrame)
    realized_as_of: pd.Timestamp = field(default_factory=_current_utc_timestamp)


def _normalize_realized_as_of(realized_as_of: object | None) -> pd.Timestamp:
    """Resolve one timestamp used to determine whether an expiration outcome is already realized."""
    if realized_as_of is None:
        return _current_utc_timestamp()

    parsed = pd.to_datetime(realized_as_of, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"realized_as_of must be a valid timestamp or date-like value. Received: {realized_as_of}")
    return pd.Timestamp(parsed).tz_localize(None)


def partition_required_outcome_requests_by_realization(
    required_observations: pd.DataFrame,
    *,
    realized_as_of: object | None = None,
) -> RequiredOutcomeRequestPartition:
    """Split required outcome rows into already-realized and still-future partitions."""
    if required_observations.empty:
        return RequiredOutcomeRequestPartition(
            realized_as_of=_normalize_realized_as_of(realized_as_of),
            eligible_required_observations=pd.DataFrame(columns=list(REQUIRED_OUTCOME_REQUEST_COLUMNS)),
            future_required_observations=pd.DataFrame(columns=list(REQUIRED_OUTCOME_REQUEST_COLUMNS)),
        )

    missing_required_columns = [
        column for column in REQUIRED_OUTCOME_REQUEST_COLUMNS if column not in required_observations.columns
    ]
    if missing_required_columns:
        missing = ", ".join(missing_required_columns)
        raise ValueError(f"required_observations is missing columns: {missing}")

    realized_as_of_ts = _normalize_realized_as_of(realized_as_of)
    eligible_mask: list[bool] = []
    for row in required_observations.to_dict("records"):
        policy = resolve_terminal_observation_policy(
            ticker=row["ticker"],
            required_outcome_horizon=row["required_outcome_horizon"],
        )
        expected_market_close = market_close_timestamp_for_event_date(
            row["expiration"],
            policy=policy,
        )
        market_close_ts = pd.to_datetime(expected_market_close, errors="coerce", utc=True)
        if pd.isna(market_close_ts):
            raise ValueError(
                "Unable to resolve market-close timestamp for required_outcome_key="
                f"{row['required_outcome_key']}."
            )
        eligible_mask.append(pd.Timestamp(market_close_ts).tz_localize(None) <= realized_as_of_ts)

    eligibility = pd.Series(eligible_mask, index=required_observations.index, dtype=bool)
    eligible = required_observations.loc[eligibility].reset_index(drop=True)
    future = required_observations.loc[~eligibility].reset_index(drop=True)
    return RequiredOutcomeRequestPartition(
        realized_as_of=realized_as_of_ts,
        eligible_required_observations=eligible,
        future_required_observations=future,
    )


def collect_required_outcome_requests_from_manifest(
    manifest_path: str | Path,
) -> pd.DataFrame:
    """Read one strict historical snapshot manifest and derive required future outcomes."""
    snapshots = load_historical_snapshots(manifest_path)
    grouped: dict[str, dict[str, Any]] = {}

    for snapshot in snapshots:
        policy = resolve_terminal_observation_policy(
            ticker=snapshot.ticker,
            required_outcome_horizon="expiration",
        )
        expirations = (
            pd.to_datetime(snapshot.option_quotes["expiration"], errors="coerce")
            .dropna()
            .dt.normalize()
            .unique()
            .tolist()
        )
        if not expirations:
            raise ValueError(
                f"Historical snapshot {snapshot.snapshot_id} carries no valid expiration values."
            )

        for expiration in sorted(pd.Timestamp(value) for value in expirations):
            required_outcome_key = build_required_outcome_key(
                ticker=snapshot.ticker,
                expiration=expiration,
                required_outcome_horizon="expiration",
                realized_outcome_measure=TERMINAL_UNDERLYING_OUTCOME_MEASURE,
            )
            record = grouped.setdefault(
                required_outcome_key,
                {
                    "required_outcome_key": required_outcome_key,
                    "ticker": snapshot.ticker,
                    "expiration": format_date_like(expiration),
                    "required_outcome_horizon": "expiration",
                    "realized_outcome_measure": TERMINAL_UNDERLYING_OUTCOME_MEASURE,
                    "terminal_price_convention": policy.terminal_price_convention,
                    "terminal_price_convention_version": policy.terminal_price_convention_version,
                    "source_snapshot_ids": set(),
                },
            )
            record["source_snapshot_ids"].add(snapshot.snapshot_id)

    records: list[dict[str, Any]] = []
    for required_outcome_key, payload in grouped.items():
        source_snapshot_ids = sorted(payload["source_snapshot_ids"])
        records.append(
            {
                "required_outcome_key": required_outcome_key,
                "ticker": payload["ticker"],
                "expiration": payload["expiration"],
                "required_outcome_horizon": payload["required_outcome_horizon"],
                "realized_outcome_measure": payload["realized_outcome_measure"],
                "terminal_price_convention": payload["terminal_price_convention"],
                "terminal_price_convention_version": payload["terminal_price_convention_version"],
                "source_snapshot_count": len(source_snapshot_ids),
                "source_snapshot_ids": ",".join(source_snapshot_ids),
            }
        )

    return pd.DataFrame(records, columns=list(REQUIRED_OUTCOME_REQUEST_COLUMNS)).sort_values(
        by=["expiration", "ticker", "required_outcome_key"],
        kind="stable",
    ).reset_index(drop=True)


def _build_realized_outcome_source(row: pd.Series) -> str:
    """Build one concise realized outcome provenance label."""
    return "|".join(
        [
            str(row["source"]).strip(),
            str(row["source_dataset"]).strip(),
            str(row["source_feed"]).strip(),
            str(row["adjustment_mode"]).strip(),
            str(row["terminal_price_convention"]).strip(),
        ]
    )


def materialize_realized_outcomes(
    *,
    required_observations: pd.DataFrame,
    realized_underlying: pd.DataFrame,
) -> pd.DataFrame:
    """Match explicit required outcome requests to normalized realized underlying rows."""
    if required_observations.empty:
        raise ValueError("required_observations must not be empty.")
    if realized_underlying.empty:
        raise ValueError("realized_underlying must not be empty.")
    missing_required_columns = [
        column for column in REQUIRED_OUTCOME_REQUEST_COLUMNS if column not in required_observations.columns
    ]
    if missing_required_columns:
        missing = ", ".join(missing_required_columns)
        raise ValueError(f"required_observations is missing columns: {missing}")

    validated_realized_underlying = validate_realized_underlying_frame(realized_underlying)

    merged = required_observations.merge(
        validated_realized_underlying,
        on="required_outcome_key",
        how="left",
        suffixes=("_required", ""),
        validate="one_to_one",
    )
    if merged["observation_id"].isna().any():
        missing_keys = merged.loc[merged["observation_id"].isna(), "required_outcome_key"].tolist()
        joined = ", ".join(missing_keys)
        raise ValueError(
            "Missing realized underlying observations for required_outcome_key values: "
            f"{joined}. Exact ticker/event-date matching is required; no forward-fill or "
            "calendar-roll convention is applied automatically."
        )

    if not merged["ticker_required"].eq(merged["ticker"]).all():
        raise ValueError("Ticker mismatch detected during outcome materialization.")
    required_expirations = pd.to_datetime(merged["expiration"], errors="coerce").dt.normalize()
    if required_expirations.isna().any():
        raise ValueError("Required observation expiration values must be valid date-like strings.")
    if not required_expirations.eq(merged["event_date"]).all():
        raise ValueError("Expiration/event_date mismatch detected during outcome materialization.")
    if not merged["required_outcome_horizon_required"].eq(merged["required_outcome_horizon"]).all():
        raise ValueError("Required outcome horizon mismatch detected during outcome materialization.")
    if not merged["realized_outcome_measure_required"].eq(merged["realized_outcome_measure"]).all():
        raise ValueError("Realized outcome measure mismatch detected during outcome materialization.")
    if not merged["terminal_price_convention_required"].eq(merged["terminal_price_convention"]).all():
        raise ValueError("Terminal price convention mismatch detected during outcome materialization.")
    if not merged["terminal_price_convention_version_required"].eq(
        merged["terminal_price_convention_version"]
    ).all():
        raise ValueError(
            "Terminal price convention version mismatch detected during outcome materialization."
        )

    records: list[dict[str, Any]] = []
    for row in merged.to_dict("records"):
        policy = resolve_terminal_observation_policy(
            ticker=row["ticker"],
            required_outcome_horizon=row["required_outcome_horizon"],
        )
        expected_market_close = market_close_timestamp_for_event_date(
            row["event_date"],
            policy=policy,
        )
        if pd.isna(row["observed_at"]) or pd.Timestamp(row["observed_at"]).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ) != expected_market_close:
            raise ValueError(
                "Observed terminal timestamp does not match the explicit market-close "
                f"policy for required_outcome_key={row['required_outcome_key']}."
            )

        records.append(
            {
                "outcome_id": f"outcome::{row['required_outcome_key']}",
                "required_outcome_key": row["required_outcome_key"],
                "ticker": row["ticker"],
                "expiration": row["event_date"],
                "required_outcome_horizon": row["required_outcome_horizon"],
                "realized_outcome_measure": row["realized_outcome_measure"],
                "realized_terminal_underlying_price": float(row["observed_price"]),
                "realized_outcome_observed_at": row["observed_at"],
                "realized_outcome_source": _build_realized_outcome_source(pd.Series(row)),
                "realized_underlying_observation_id": row["observation_id"],
                "terminal_price_convention": row["terminal_price_convention"],
                "terminal_price_convention_version": row["terminal_price_convention_version"],
                "observed_market_session": row["observed_market_session"],
                "market_close_timestamp": row["market_close_timestamp"],
                "source_dataset": row["source_dataset"],
                "source_feed": row["source_feed"],
                "adjustment_mode": row["adjustment_mode"],
                "provenance_artifact_id": row["provenance_artifact_id"],
                "source_snapshot_count": row["source_snapshot_count"],
                "source_snapshot_ids": row["source_snapshot_ids"],
            }
        )

    outcome_frame = pd.DataFrame(records)
    validated = validate_realized_outcome_frame(outcome_frame)

    for column in outcome_frame.columns:
        if column not in OUTCOME_REQUIRED_COLUMNS:
            validated[column] = outcome_frame[column].values

    return validated.sort_values(
        by=["expiration", "outcome_id"],
        kind="stable",
    ).reset_index(drop=True)


def materialize_realized_outcomes_from_snapshot_manifest(
    *,
    manifest_path: str | Path,
    realized_underlying_paths: list[str | Path],
    realized_as_of: object | None = None,
) -> MaterializedRealizedOutcomeArtifacts:
    """Materialize contract-valid realized outcomes from strict snapshots plus normalized bars."""
    required_observations = collect_required_outcome_requests_from_manifest(manifest_path)
    partition = partition_required_outcome_requests_by_realization(
        required_observations,
        realized_as_of=realized_as_of,
    )
    realized_underlying = load_realized_underlying_artifacts(realized_underlying_paths)
    if partition.eligible_required_observations.empty:
        outcomes = pd.DataFrame(columns=list(OUTCOME_REQUIRED_COLUMNS))
    else:
        outcomes = materialize_realized_outcomes(
            required_observations=partition.eligible_required_observations,
            realized_underlying=realized_underlying,
        )
    return MaterializedRealizedOutcomeArtifacts(
        required_observations=required_observations,
        eligible_required_observations=partition.eligible_required_observations,
        future_required_observations=partition.future_required_observations,
        outcomes=outcomes,
        realized_as_of=partition.realized_as_of,
    )


def write_realized_outcomes(outcomes: pd.DataFrame, output_path: str | Path) -> Path:
    """Validate and write one realized outcome artifact CSV."""
    validated = validate_realized_outcome_frame(outcomes)
    for column in outcomes.columns:
        if column not in validated.columns:
            validated[column] = outcomes[column].values
    serialized = validated.copy()
    serialized["expiration"] = serialized["expiration"].map(format_date_like)
    serialized["realized_outcome_observed_at"] = serialized["realized_outcome_observed_at"].map(
        format_utc_timestamp
    )
    if "market_close_timestamp" in serialized.columns:
        serialized["market_close_timestamp"] = serialized["market_close_timestamp"].map(
            format_utc_timestamp
        )

    path = ensure_parent(output_path)
    serialized.to_csv(path, index=False)
    return path
