"""Forward-only time split helpers for probability calibration research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from options_edge_scanner.calibration.contracts import validate_probability_prediction_frame


@dataclass(frozen=True)
class ForwardEvaluationWindow:
    """One forward-only train/test split definition."""

    split_id: str
    split_mode: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_count: int
    test_count: int


def _sorted_prediction_timestamps(predictions: pd.DataFrame) -> pd.Series:
    """Return unique sorted prediction timestamps from validated predictions."""
    validated = validate_probability_prediction_frame(predictions)
    return validated["prediction_timestamp"].drop_duplicates().sort_values().reset_index(drop=True)


def _count_rows_between(
    predictions: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> int:
    """Count predictions whose timestamp falls within one inclusive interval."""
    timestamps = predictions["prediction_timestamp"]
    return int(timestamps.between(start, end, inclusive="both").sum())


def build_fixed_holdout_window(
    predictions: pd.DataFrame,
    *,
    holdout_start: Any,
) -> list[ForwardEvaluationWindow]:
    """Build one deterministic fixed holdout split."""
    validated = validate_probability_prediction_frame(predictions)
    holdout_start_ts = pd.to_datetime(holdout_start, errors="coerce", utc=True)
    if pd.isna(holdout_start_ts):
        raise ValueError(f"holdout_start must be a valid timestamp, got: {holdout_start}")
    holdout_start_ts = pd.Timestamp(holdout_start_ts).tz_localize(None)

    train_rows = validated.loc[validated["prediction_timestamp"] < holdout_start_ts].copy()
    test_rows = validated.loc[validated["prediction_timestamp"] >= holdout_start_ts].copy()
    if train_rows.empty or test_rows.empty:
        raise ValueError("Fixed holdout requires at least one train row and one test row.")

    return [
        ForwardEvaluationWindow(
            split_id="holdout_001",
            split_mode="holdout",
            train_start=pd.Timestamp(train_rows["prediction_timestamp"].min()),
            train_end=pd.Timestamp(train_rows["prediction_timestamp"].max()),
            test_start=pd.Timestamp(test_rows["prediction_timestamp"].min()),
            test_end=pd.Timestamp(test_rows["prediction_timestamp"].max()),
            train_count=int(len(train_rows)),
            test_count=int(len(test_rows)),
        )
    ]


def build_expanding_windows(
    predictions: pd.DataFrame,
    *,
    min_train_size: int,
    test_size: int,
    step_size: int = 1,
) -> list[ForwardEvaluationWindow]:
    """Build expanding-window forward splits from ordered prediction timestamps."""
    if min_train_size <= 0 or test_size <= 0 or step_size <= 0:
        raise ValueError("min_train_size, test_size, and step_size must be positive.")

    validated = validate_probability_prediction_frame(predictions)
    unique_timestamps = _sorted_prediction_timestamps(validated)
    windows: list[ForwardEvaluationWindow] = []

    split_number = 1
    train_end_index = min_train_size - 1
    while train_end_index + test_size < len(unique_timestamps):
        train_start = pd.Timestamp(unique_timestamps.iloc[0])
        train_end = pd.Timestamp(unique_timestamps.iloc[train_end_index])
        test_start = pd.Timestamp(unique_timestamps.iloc[train_end_index + 1])
        test_end = pd.Timestamp(unique_timestamps.iloc[train_end_index + test_size])

        windows.append(
            ForwardEvaluationWindow(
                split_id=f"expanding_{split_number:03d}",
                split_mode="expanding",
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_count=_count_rows_between(validated, start=train_start, end=train_end),
                test_count=_count_rows_between(validated, start=test_start, end=test_end),
            )
        )
        split_number += 1
        train_end_index += step_size

    if not windows:
        raise ValueError("No expanding windows fit the provided sizes.")
    return windows


def build_rolling_windows(
    predictions: pd.DataFrame,
    *,
    train_size: int,
    test_size: int,
    step_size: int = 1,
) -> list[ForwardEvaluationWindow]:
    """Build rolling forward splits from ordered prediction timestamps."""
    if train_size <= 0 or test_size <= 0 or step_size <= 0:
        raise ValueError("train_size, test_size, and step_size must be positive.")

    validated = validate_probability_prediction_frame(predictions)
    unique_timestamps = _sorted_prediction_timestamps(validated)
    windows: list[ForwardEvaluationWindow] = []

    split_number = 1
    train_start_index = 0
    while train_start_index + train_size + test_size <= len(unique_timestamps):
        train_start = pd.Timestamp(unique_timestamps.iloc[train_start_index])
        train_end = pd.Timestamp(unique_timestamps.iloc[train_start_index + train_size - 1])
        test_start = pd.Timestamp(unique_timestamps.iloc[train_start_index + train_size])
        test_end = pd.Timestamp(unique_timestamps.iloc[train_start_index + train_size + test_size - 1])

        windows.append(
            ForwardEvaluationWindow(
                split_id=f"rolling_{split_number:03d}",
                split_mode="rolling",
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_count=_count_rows_between(validated, start=train_start, end=train_end),
                test_count=_count_rows_between(validated, start=test_start, end=test_end),
            )
        )
        split_number += 1
        train_start_index += step_size

    if not windows:
        raise ValueError("No rolling windows fit the provided sizes.")
    return windows
