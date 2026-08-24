"""Historical effectiveness evaluation for scanner-ranked opportunities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pandas as pd

from options_edge_scanner.calibration import (
    build_required_outcome_key,
    evaluate_probability_predictions,
    export_scanner_probability_predictions,
    validate_realized_outcome_frame,
)
from options_edge_scanner.calibration.contracts import (
    CALIBRATION_SUMMARY_COLUMNS,
    EVALUATION_OBSERVATION_COLUMNS as CALIBRATION_EVALUATION_OBSERVATION_COLUMNS,
    RELIABILITY_BIN_COLUMNS,
)
from options_edge_scanner.models.spread_ev_calculator import TRANSACTION_COST


EFFECTIVENESS_REQUIRED_OPPORTUNITY_COLUMNS = (
    "ticker",
    "snapshot_id",
    "quote_observed_at",
    "as_of",
    "expiration",
    "spread_type",
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "width",
    "debit",
    "quoted_debit",
    "max_profit",
    "max_loss",
    "expected_value",
    "probability_of_profit",
    "ranking_score",
    "probability_model_name",
    "probability_model_version",
    "predicted_event_name",
    "predicted_event_direction",
    "predicted_event_operator",
    "predicted_event_threshold",
    "predicted_event_horizon",
    "underlying_price",
    "implied_volatility",
)

_REQUIRED_STRING_COLUMNS = (
    "ticker",
    "snapshot_id",
    "spread_type",
    "probability_model_name",
    "probability_model_version",
    "predicted_event_name",
    "predicted_event_direction",
    "predicted_event_operator",
    "predicted_event_horizon",
)

_REQUIRED_NUMERIC_COLUMNS = (
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "width",
    "debit",
    "quoted_debit",
    "max_profit",
    "max_loss",
    "expected_value",
    "probability_of_profit",
    "ranking_score",
    "predicted_event_threshold",
    "underlying_price",
    "implied_volatility",
)

_OPTIONAL_NUMERIC_COLUMNS = (
    "days_to_expiration",
    "theoretical_expected_value",
    "theoretical_edge_pct",
    "quoted_max_profit",
    "quoted_max_loss",
    "liquidity_score",
    "spread_bid",
    "spread_ask",
    "spread_market_width",
    "entry_slippage",
    "entry_slippage_pct",
    "entry_fill_fraction_of_market_width",
    "spread_min_volume",
    "spread_min_open_interest",
    "long_delta",
    "short_delta",
    "long_open_interest",
    "short_open_interest",
    "long_volume",
    "short_volume",
    "selection_rank",
    "edge_pct",
)

_OPTIONAL_STRING_COLUMNS = (
    "snapshot_source",
    "input_path",
    "source_metadata_path",
    "entry_price_policy",
    "ev_method",
    "theoretical_ev_method",
    "underlying_price_source",
    "option_type",
)

EFFECTIVENESS_OBSERVATION_COLUMNS = (
    "prediction_id",
    "snapshot_id",
    "snapshot_source",
    "ticker",
    "prediction_timestamp",
    "quote_observed_at",
    "as_of",
    "expiration",
    "spread_type",
    "option_type",
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "width",
    "days_to_expiration",
    "selection_rank",
    "debit",
    "quoted_debit",
    "spread_ask",
    "spread_bid",
    "spread_market_width",
    "entry_slippage",
    "entry_slippage_pct",
    "entry_fill_fraction_of_market_width",
    "entry_price_policy",
    "liquidity_score",
    "expected_value",
    "theoretical_expected_value",
    "edge_pct",
    "probability_of_profit",
    "predicted_probability",
    "probability_model_name",
    "probability_model_version",
    "predicted_event_name",
    "predicted_event_direction",
    "predicted_event_operator",
    "predicted_event_threshold",
    "predicted_event_horizon",
    "required_outcome_key",
    "observation_group_id",
    "input_path",
    "source_metadata_path",
    "realized_terminal_underlying_price",
    "realized_outcome_observed_at",
    "realized_outcome_source",
    "realized_event",
    "spread_expiration_value",
    "realized_pnl_quoted_gross",
    "realized_pnl_quoted",
    "realized_pnl_executable_gross",
    "realized_pnl_executable",
    "realized_pnl_ask_gross",
    "realized_pnl_ask",
    "realized_positive_pnl_quoted",
    "realized_positive_pnl_executable",
    "realized_positive_pnl_ask",
    "realized_return_on_risk_executable",
    "expected_minus_realized_pnl_executable",
    "breakeven_moneyness_pct",
    "spread_market_width_pct",
    "dte_bucket",
    "breakeven_moneyness_bucket",
    "liquidity_bucket",
    "spread_width_bucket",
    "volatility_regime_bucket",
    "prediction_quarter",
)

EFFECTIVENESS_EXCLUSION_COLUMNS = (
    "prediction_id",
    "snapshot_id",
    "snapshot_source",
    "ticker",
    "prediction_timestamp",
    "quote_observed_at",
    "as_of",
    "expiration",
    "spread_type",
    "option_type",
    "lower_strike",
    "upper_strike",
    "long_strike",
    "short_strike",
    "width",
    "days_to_expiration",
    "selection_rank",
    "expected_value",
    "probability_of_profit",
    "ranking_score",
    "required_outcome_key",
    "observation_group_id",
    "input_path",
    "source_metadata_path",
    "evaluation_status",
    "exclusion_reason",
    "exclusion_detail",
    "required_event_date",
    "issue_classification",
    "previous_available_event_date",
    "next_available_event_date",
)

EFFECTIVENESS_EXCLUSION_SUMMARY_COLUMNS = (
    "exclusion_reason",
    "required_event_date",
    "excluded_opportunity_count",
    "excluded_required_outcome_key_count",
    "snapshot_count",
    "affected_spread_type_count",
    "affected_spread_types",
)

GROUP_SUMMARY_COLUMNS = (
    "observation_count",
    "outcome_cluster_count",
    "snapshot_count",
    "event_count",
    "mean_predicted_probability",
    "observed_event_rate",
    "observed_event_rate_ci_lower",
    "observed_event_rate_ci_upper",
    "realized_profit_count_executable",
    "realized_profit_rate_executable",
    "realized_profit_rate_ci_lower",
    "realized_profit_rate_ci_upper",
    "mean_expected_value",
    "total_expected_value",
    "mean_realized_pnl_executable",
    "mean_realized_pnl_executable_ci_lower",
    "mean_realized_pnl_executable_ci_upper",
    "median_realized_pnl_executable",
    "total_realized_pnl_executable",
    "mean_realized_pnl_quoted",
    "total_realized_pnl_quoted",
    "mean_ranking_score",
    "mean_liquidity_score",
    "mean_days_to_expiration",
    "mean_implied_volatility",
)

METRIC_BUCKET_COLUMNS = (
    "metric_name",
    "effective_bucket_count",
    "bucket_index",
    "bucket_label",
    "metric_min",
    "metric_max",
    "metric_mean",
    *GROUP_SUMMARY_COLUMNS,
)

SEGMENT_SUMMARY_COLUMNS = (
    "segment_dimension",
    "segment_value",
    *GROUP_SUMMARY_COLUMNS,
)

EXECUTION_SENSITIVITY_COLUMNS = (
    "scenario_name",
    "entry_price_reference",
    "priced_observation_count",
    "outcome_cluster_count",
    "mean_entry_price",
    "mean_slippage_vs_quoted_debit",
    "mean_realized_pnl",
    "mean_realized_pnl_ci_lower",
    "mean_realized_pnl_ci_upper",
    "total_realized_pnl",
    "profit_rate",
    "profit_rate_ci_lower",
    "profit_rate_ci_upper",
)

TAIL_CONCENTRATION_COLUMNS = (
    "metric_name",
    "observation_count",
    "positive_pnl_total",
    "negative_pnl_total",
    "max_winner",
    "max_loser",
    "top_1_positive_pnl_share",
    "top_5_positive_pnl_share",
    "top_10pct_positive_pnl_share",
    "top_1_abs_pnl_share",
    "top_5_abs_pnl_share",
    "top_10pct_abs_pnl_share",
    "winsorized_mean_5pct",
    "winsorized_mean_10pct",
)

EFFECTIVENESS_SUMMARY_COLUMNS = (
    "input_opportunity_count",
    "evaluated_opportunity_count",
    "excluded_opportunity_count",
    "evaluation_coverage_rate",
    "excluded_opportunity_rate",
    "excluded_missing_outcome_count",
    "excluded_missing_realized_underlying_count",
    "excluded_future_outcome_count",
    "missing_realized_event_date_count",
    "missing_realized_event_dates",
    "available_outcome_count",
    "evaluated_outcome_count",
    "shared_outcome_key_count",
    "evaluation_status",
    "mean_predicted_probability",
    "observed_event_rate",
    "observed_event_rate_ci_lower",
    "observed_event_rate_ci_upper",
    "realized_profit_rate_executable",
    "realized_profit_rate_ci_lower",
    "realized_profit_rate_ci_upper",
    "mean_expected_value",
    "mean_realized_pnl_executable",
    "mean_realized_pnl_executable_ci_lower",
    "mean_realized_pnl_executable_ci_upper",
    "mean_realized_pnl_quoted",
    "total_expected_value",
    "total_realized_pnl_executable",
    "total_realized_pnl_quoted",
    "ranking_score_spearman_realized_pnl",
    "ranking_score_spearman_realized_event",
    "expected_value_spearman_realized_pnl",
    "probability_spearman_realized_event",
    "ranking_score_auc_realized_event",
    "ranking_score_auc_realized_profit",
    "expected_value_auc_realized_profit",
    "probability_auc_realized_event",
    "ranking_score_top_minus_bottom_mean_realized_pnl",
    "ranking_score_top_minus_bottom_profit_rate",
    "expected_value_top_minus_bottom_mean_realized_pnl",
    "expected_value_top_minus_bottom_profit_rate",
)

_DEFAULT_METRIC_COLUMNS = (
    "ranking_score",
    "expected_value",
    "probability_of_profit",
)
_DEFAULT_SEGMENT_COLUMNS = (
    "dte_bucket",
    "spread_type",
    "breakeven_moneyness_bucket",
    "liquidity_bucket",
    "spread_width_bucket",
    "volatility_regime_bucket",
    "prediction_quarter",
)
_Z_95 = 1.959963984540054
_EXCLUSION_DETAIL_COLUMNS = (
    "required_outcome_key",
    "exclusion_reason",
    "exclusion_detail",
    "required_event_date",
    "issue_classification",
    "previous_available_event_date",
    "next_available_event_date",
)


@dataclass(frozen=True)
class EffectivenessEvaluationArtifacts:
    """Machine-readable effectiveness outputs plus a concise markdown report."""

    predictions: pd.DataFrame
    calibration_summary: pd.DataFrame
    calibration_bins: pd.DataFrame
    calibration_observations: pd.DataFrame
    observations: pd.DataFrame
    exclusions: pd.DataFrame
    exclusion_summary: pd.DataFrame
    summary: pd.DataFrame
    metric_buckets: pd.DataFrame
    segment_summary: pd.DataFrame
    execution_sensitivity: pd.DataFrame
    tail_concentration: pd.DataFrame
    report_markdown: str


def _non_empty_string_series(series: pd.Series, *, column: str) -> pd.Series:
    normalized = series.astype("string").str.strip()
    if normalized.isna().any() or normalized.eq("").any():
        raise ValueError(f"{column} must be present and non-empty.")
    return normalized


def _parse_numeric_series(series: pd.Series, *, column: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{column} must contain numeric values.")
    return numeric.astype(float)


def _parse_optional_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _parse_timestamp_series(series: pd.Series, *, column: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError(f"{column} must contain valid timestamps.")
    return parsed.dt.tz_localize(None)


def _parse_date_series(series: pd.Series, *, column: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError(f"{column} must contain valid date-like values.")
    return parsed.dt.tz_localize(None).dt.normalize()


def _empty_calibration_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.DataFrame(columns=list(CALIBRATION_SUMMARY_COLUMNS)),
        pd.DataFrame(columns=list(RELIABILITY_BIN_COLUMNS)),
        pd.DataFrame(columns=list(CALIBRATION_EVALUATION_OBSERVATION_COLUMNS)),
    )


def _normalize_exclusion_details(exclusion_details: pd.DataFrame | None) -> pd.DataFrame:
    if exclusion_details is None or exclusion_details.empty:
        return pd.DataFrame(columns=list(_EXCLUSION_DETAIL_COLUMNS))

    missing_columns = [
        column for column in ("required_outcome_key", "exclusion_reason")
        if column not in exclusion_details.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"exclusion_details is missing columns: {missing}")

    working = exclusion_details.copy().reset_index(drop=True)
    working["required_outcome_key"] = _non_empty_string_series(
        working["required_outcome_key"],
        column="required_outcome_key",
    )
    working["exclusion_reason"] = _non_empty_string_series(
        working["exclusion_reason"],
        column="exclusion_reason",
    )
    if "required_event_date" in working.columns:
        present_mask = working["required_event_date"].notna()
        parsed_required_event_date = pd.Series(pd.NaT, index=working.index, dtype="datetime64[ns]")
        if present_mask.any():
            parsed_required_event_date.loc[present_mask] = _parse_date_series(
                working.loc[present_mask, "required_event_date"],
                column="required_event_date",
            ).values
        working = working.drop(columns=["required_event_date"])
        working["required_event_date"] = parsed_required_event_date
    else:
        working["required_event_date"] = pd.NaT

    for column in (
        "exclusion_detail",
        "issue_classification",
        "previous_available_event_date",
        "next_available_event_date",
    ):
        if column in working.columns:
            working[column] = working[column].astype("string").str.strip()
        else:
            working[column] = pd.NA

    if working["required_outcome_key"].duplicated().any():
        raise ValueError("exclusion_details.required_outcome_key values must be unique.")

    return working.loc[:, list(_EXCLUSION_DETAIL_COLUMNS)].reset_index(drop=True)


def _build_exclusion_frame(
    excluded_rows: pd.DataFrame,
    *,
    exclusion_details: pd.DataFrame,
) -> pd.DataFrame:
    if excluded_rows.empty:
        return pd.DataFrame(columns=list(EFFECTIVENESS_EXCLUSION_COLUMNS))

    working = excluded_rows.copy()
    if not exclusion_details.empty:
        working = working.merge(
            exclusion_details,
            on="required_outcome_key",
            how="left",
            validate="many_to_one",
        )
    else:
        for column in _EXCLUSION_DETAIL_COLUMNS:
            if column == "required_outcome_key":
                continue
            working[column] = pd.NA

    working["evaluation_status"] = "excluded"
    working["exclusion_reason"] = (
        working["exclusion_reason"]
        .astype("string")
        .fillna("missing_realized_outcome")
    )
    working["exclusion_detail"] = (
        working["exclusion_detail"]
        .astype("string")
        .fillna("No matching realized outcome was available from the supplied outcome set.")
    )
    working["required_event_date"] = working["required_event_date"].where(
        working["required_event_date"].notna(),
        working["expiration"],
    )
    for column in EFFECTIVENESS_EXCLUSION_COLUMNS:
        if column not in working.columns:
            working[column] = pd.NA

    return (
        working.sort_values(
            by=["prediction_timestamp", "prediction_id"],
            kind="stable",
        )
        .loc[:, list(EFFECTIVENESS_EXCLUSION_COLUMNS)]
        .reset_index(drop=True)
    )


def _build_exclusion_summary(exclusions: pd.DataFrame) -> pd.DataFrame:
    if exclusions.empty:
        return pd.DataFrame(columns=list(EFFECTIVENESS_EXCLUSION_SUMMARY_COLUMNS))

    working = exclusions.copy()
    working["required_event_date"] = pd.to_datetime(
        working["required_event_date"],
        errors="coerce",
        utc=True,
    ).dt.tz_localize(None).dt.normalize()

    records: list[dict[str, Any]] = []
    grouped = working.groupby(["exclusion_reason", "required_event_date"], dropna=False, sort=True)
    for (exclusion_reason, required_event_date), rows in grouped:
        spread_types = sorted(
            {
                str(value).strip()
                for value in rows["spread_type"].dropna().astype("string").tolist()
                if str(value).strip()
            }
        )
        records.append(
            {
                "exclusion_reason": str(exclusion_reason),
                "required_event_date": (
                    pd.Timestamp(required_event_date).strftime("%Y-%m-%d")
                    if pd.notna(required_event_date)
                    else "unknown"
                ),
                "excluded_opportunity_count": int(len(rows)),
                "excluded_required_outcome_key_count": int(rows["required_outcome_key"].nunique()),
                "snapshot_count": int(rows["snapshot_id"].nunique()),
                "affected_spread_type_count": int(len(spread_types)),
                "affected_spread_types": ",".join(spread_types),
            }
        )

    return pd.DataFrame.from_records(
        records,
        columns=list(EFFECTIVENESS_EXCLUSION_SUMMARY_COLUMNS),
    )


def validate_effectiveness_opportunity_frame(opportunities: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize historical scanner opportunities for effectiveness work."""
    if opportunities.empty:
        raise ValueError("opportunities must not be empty.")

    missing_columns = [
        column for column in EFFECTIVENESS_REQUIRED_OPPORTUNITY_COLUMNS if column not in opportunities.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Scanner opportunities are missing effectiveness columns: {missing}")

    working = opportunities.copy().reset_index(drop=True)
    for column in _REQUIRED_STRING_COLUMNS:
        working[column] = _non_empty_string_series(working[column], column=column)

    working["ticker"] = working["ticker"].str.upper()
    working["quote_observed_at"] = _parse_timestamp_series(
        working["quote_observed_at"],
        column="quote_observed_at",
    )
    working["as_of"] = _parse_timestamp_series(working["as_of"], column="as_of")
    working["expiration"] = _parse_date_series(working["expiration"], column="expiration")

    for column in _REQUIRED_NUMERIC_COLUMNS:
        working[column] = _parse_numeric_series(working[column], column=column)

    for column in _OPTIONAL_NUMERIC_COLUMNS:
        if column in working.columns:
            working[column] = _parse_optional_numeric_series(working[column])
        else:
            working[column] = float("nan")

    for column in _OPTIONAL_STRING_COLUMNS:
        if column in working.columns:
            working[column] = working[column].astype("string").str.strip()
        else:
            working[column] = pd.NA

    if not working["probability_of_profit"].between(0.0, 1.0, inclusive="both").all():
        raise ValueError("probability_of_profit must be within [0, 1].")
    if not working["width"].gt(0).all():
        raise ValueError("width must be strictly positive.")
    if not working["debit"].gt(0).all():
        raise ValueError("debit must be strictly positive.")
    if not working["quoted_debit"].gt(0).all():
        raise ValueError("quoted_debit must be strictly positive.")
    if not working["underlying_price"].gt(0).all():
        raise ValueError("underlying_price must be strictly positive.")
    if not working["implied_volatility"].gt(0).all():
        raise ValueError("implied_volatility must be strictly positive.")
    if not working["predicted_event_horizon"].eq("expiration").all():
        raise ValueError(
            "Current effectiveness evaluation only supports expiration-horizon opportunities."
        )

    if "days_to_expiration" in opportunities.columns and working["days_to_expiration"].notna().any():
        working["days_to_expiration"] = _parse_optional_numeric_series(working["days_to_expiration"])
    else:
        working["days_to_expiration"] = (
            working["expiration"] - working["as_of"].dt.normalize()
        ).dt.days.astype(float)

    expected_outcome_keys = pd.Series(
        [
            build_required_outcome_key(
                ticker=row["ticker"],
                expiration=row["expiration"],
                required_outcome_horizon="expiration",
            )
            for row in working.to_dict("records")
        ],
        index=working.index,
        dtype="string",
    )
    if "required_outcome_key" in working.columns:
        existing = working["required_outcome_key"].astype("string").str.strip()
        mismatch = existing.notna() & existing.ne("") & existing.ne(expected_outcome_keys)
        if mismatch.any():
            raise ValueError(
                "required_outcome_key does not match the scanner opportunity contract fields."
            )
    working["required_outcome_key"] = expected_outcome_keys

    return working


def _clustered_mean_ci(
    values: pd.Series,
    clusters: pd.Series,
) -> tuple[float, float, float, int, int]:
    frame = pd.DataFrame({"value": values, "cluster": clusters})
    frame = frame.dropna(subset=["value", "cluster"]).copy()
    if frame.empty:
        return float("nan"), float("nan"), float("nan"), 0, 0

    mean_value = float(frame["value"].mean())
    observation_count = int(len(frame))
    grouped = frame.groupby("cluster", dropna=False)["value"].agg(["sum", "count"])
    cluster_count = int(len(grouped))
    if observation_count <= 1:
        return mean_value, float("nan"), float("nan"), observation_count, cluster_count

    if cluster_count <= 1:
        se = float(frame["value"].std(ddof=1)) / math.sqrt(observation_count)
    else:
        centered_cluster_sums = grouped["sum"] - (grouped["count"] * mean_value)
        variance = float(
            (cluster_count / (cluster_count - 1.0))
            * centered_cluster_sums.pow(2).sum()
            / (observation_count ** 2)
        )
        se = math.sqrt(max(variance, 0.0))

    return (
        mean_value,
        float(mean_value - (_Z_95 * se)),
        float(mean_value + (_Z_95 * se)),
        observation_count,
        cluster_count,
    )


def _safe_spearman(values_a: pd.Series, values_b: pd.Series) -> float:
    frame = pd.DataFrame({"a": values_a, "b": values_b}).dropna()
    if len(frame) < 2:
        return float("nan")
    if frame["a"].nunique() < 2 or frame["b"].nunique() < 2:
        return float("nan")
    return float(frame["a"].corr(frame["b"], method="spearman"))


def _binary_auc(scores: pd.Series, labels: pd.Series) -> float:
    frame = pd.DataFrame({"score": scores, "label": labels}).dropna()
    if frame.empty:
        return float("nan")

    frame["label"] = pd.to_numeric(frame["label"], errors="coerce")
    frame = frame.loc[frame["label"].isin([0.0, 1.0])].copy()
    positive_count = int((frame["label"] == 1.0).sum())
    negative_count = int((frame["label"] == 0.0).sum())
    if positive_count == 0 or negative_count == 0:
        return float("nan")

    ranks = frame["score"].rank(method="average", ascending=True)
    positive_rank_sum = float(ranks.loc[frame["label"] == 1.0].sum())
    auc = (
        positive_rank_sum - ((positive_count * (positive_count + 1)) / 2.0)
    ) / (positive_count * negative_count)
    return float(auc)


def _assign_ordered_buckets(
    values: pd.Series,
    *,
    bucket_count: int,
    higher_is_better: bool = True,
) -> tuple[pd.Series, int]:
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(pd.NA, index=values.index, dtype="string"), 0

    effective_bucket_count = min(int(bucket_count), int(len(valid)))
    ordered_positions = numeric.rank(method="first", ascending=not higher_is_better)
    bucket_index = pd.Series(pd.NA, index=values.index, dtype="Int64")
    bucket_index.loc[ordered_positions.notna()] = (
        (((ordered_positions.loc[ordered_positions.notna()] - 1) * effective_bucket_count) // len(valid)) + 1
    ).astype("int64")
    labels = bucket_index.map(
        lambda value: (
            pd.NA
            if pd.isna(value)
            else f"{int(value):02d}/{effective_bucket_count:02d}"
        )
    ).astype("string")
    return labels, effective_bucket_count


def _fixed_bucket_labels(
    values: pd.Series,
    *,
    bins: Sequence[float],
    labels: Sequence[str],
) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    bucketed = pd.cut(
        numeric,
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=True,
    )
    return bucketed.astype("string").fillna("unknown")


def _prediction_quarter_label(timestamp: pd.Timestamp) -> str:
    quarter = ((int(timestamp.month) - 1) // 3) + 1
    return f"{int(timestamp.year)}Q{quarter}"


def _compute_expiration_value(row: pd.Series) -> float:
    terminal_price = float(row["realized_terminal_underlying_price"])
    lower_strike = float(row["lower_strike"])
    upper_strike = float(row["upper_strike"])
    width = float(row["width"])
    spread_type = str(row["spread_type"]).strip().lower()

    if spread_type == "bull_call_debit":
        intrinsic = max(terminal_price - lower_strike, 0.0) - max(terminal_price - upper_strike, 0.0)
    elif spread_type == "bear_put_debit":
        intrinsic = max(upper_strike - terminal_price, 0.0) - max(lower_strike - terminal_price, 0.0)
    else:
        raise ValueError(
            "Current effectiveness evaluation only supports bull_call_debit and bear_put_debit."
        )

    return float(min(max(intrinsic, 0.0), width))


def _compute_realized_event(row: pd.Series) -> int:
    terminal_price = float(row["realized_terminal_underlying_price"])
    threshold = float(row["predicted_event_threshold"])
    direction = str(row["predicted_event_direction"]).strip()
    operator = str(row["predicted_event_operator"]).strip()

    if direction == "above" and operator == ">":
        return int(terminal_price > threshold)
    if direction == "below" and operator == "<":
        return int(terminal_price < threshold)
    raise ValueError(
        "predicted_event_direction and predicted_event_operator are unsupported or inconsistent."
    )


def _summarize_group(frame: pd.DataFrame) -> dict[str, Any]:
    mean_event, event_low, event_high, observation_count, outcome_cluster_count = _clustered_mean_ci(
        frame["realized_event"],
        frame["required_outcome_key"],
    )
    mean_profit, profit_low, profit_high, _obs_count, _cluster_count = _clustered_mean_ci(
        frame["realized_positive_pnl_executable"],
        frame["required_outcome_key"],
    )
    mean_pnl, pnl_low, pnl_high, _obs_count_two, _cluster_count_two = _clustered_mean_ci(
        frame["realized_pnl_executable"],
        frame["required_outcome_key"],
    )

    return {
        "observation_count": observation_count,
        "outcome_cluster_count": outcome_cluster_count,
        "snapshot_count": int(frame["snapshot_id"].nunique()),
        "event_count": int(frame["realized_event"].sum()),
        "mean_predicted_probability": float(frame["predicted_probability"].mean()),
        "observed_event_rate": mean_event,
        "observed_event_rate_ci_lower": event_low,
        "observed_event_rate_ci_upper": event_high,
        "realized_profit_count_executable": int(frame["realized_positive_pnl_executable"].sum()),
        "realized_profit_rate_executable": mean_profit,
        "realized_profit_rate_ci_lower": profit_low,
        "realized_profit_rate_ci_upper": profit_high,
        "mean_expected_value": float(frame["expected_value"].mean()),
        "total_expected_value": float(frame["expected_value"].sum()),
        "mean_realized_pnl_executable": mean_pnl,
        "mean_realized_pnl_executable_ci_lower": pnl_low,
        "mean_realized_pnl_executable_ci_upper": pnl_high,
        "median_realized_pnl_executable": float(frame["realized_pnl_executable"].median()),
        "total_realized_pnl_executable": float(frame["realized_pnl_executable"].sum()),
        "mean_realized_pnl_quoted": float(frame["realized_pnl_quoted"].mean()),
        "total_realized_pnl_quoted": float(frame["realized_pnl_quoted"].sum()),
        "mean_ranking_score": float(frame["ranking_score"].mean()),
        "mean_liquidity_score": float(frame["liquidity_score"].mean())
        if frame["liquidity_score"].notna().any()
        else float("nan"),
        "mean_days_to_expiration": float(frame["days_to_expiration"].mean()),
        "mean_implied_volatility": float(frame["implied_volatility"].mean()),
    }


def _build_metric_bucket_summary(
    observations: pd.DataFrame,
    *,
    metric_name: str,
    bucket_count: int,
) -> pd.DataFrame:
    bucket_labels, effective_bucket_count = _assign_ordered_buckets(
        observations[metric_name],
        bucket_count=bucket_count,
        higher_is_better=True,
    )
    if effective_bucket_count == 0:
        return pd.DataFrame(columns=list(METRIC_BUCKET_COLUMNS))

    working = observations.copy()
    working["_bucket_label"] = bucket_labels
    working["_bucket_index"] = (
        working["_bucket_label"].astype("string").str.split("/", n=1).str[0].astype("Int64")
    )

    records: list[dict[str, Any]] = []
    for bucket_index in range(1, effective_bucket_count + 1):
        bucket_rows = working.loc[working["_bucket_index"] == bucket_index].copy()
        if bucket_rows.empty:
            continue
        summary = _summarize_group(bucket_rows)
        records.append(
            {
                "metric_name": metric_name,
                "effective_bucket_count": effective_bucket_count,
                "bucket_index": bucket_index,
                "bucket_label": f"{bucket_index:02d}/{effective_bucket_count:02d}",
                "metric_min": float(bucket_rows[metric_name].min()),
                "metric_max": float(bucket_rows[metric_name].max()),
                "metric_mean": float(bucket_rows[metric_name].mean()),
                **summary,
            }
        )

    return pd.DataFrame.from_records(records, columns=list(METRIC_BUCKET_COLUMNS))


def _build_segment_summary(
    observations: pd.DataFrame,
    *,
    segment_columns: Iterable[str],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for segment_column in segment_columns:
        if segment_column not in observations.columns:
            continue
        grouped = observations.groupby(segment_column, dropna=False, sort=True)
        for segment_value, segment_rows in grouped:
            if segment_rows.empty:
                continue
            value = "unknown" if pd.isna(segment_value) else str(segment_value)
            summary = _summarize_group(segment_rows)
            records.append(
                {
                    "segment_dimension": segment_column,
                    "segment_value": value,
                    **summary,
                }
            )

    if not records:
        return pd.DataFrame(columns=list(SEGMENT_SUMMARY_COLUMNS))
    return pd.DataFrame.from_records(records, columns=list(SEGMENT_SUMMARY_COLUMNS))


def _build_execution_sensitivity(observations: pd.DataFrame) -> pd.DataFrame:
    scenario_specs = (
        ("quoted_mid", "quoted_debit"),
        ("baseline_executable", "debit"),
        ("displayed_ask", "spread_ask"),
    )
    records: list[dict[str, Any]] = []
    for scenario_name, entry_price_column in scenario_specs:
        prices = pd.to_numeric(observations[entry_price_column], errors="coerce")
        priced = observations.loc[prices.notna()].copy()
        if priced.empty:
            records.append(
                {
                    "scenario_name": scenario_name,
                    "entry_price_reference": entry_price_column,
                    "priced_observation_count": 0,
                    "outcome_cluster_count": 0,
                    "mean_entry_price": float("nan"),
                    "mean_slippage_vs_quoted_debit": float("nan"),
                    "mean_realized_pnl": float("nan"),
                    "mean_realized_pnl_ci_lower": float("nan"),
                    "mean_realized_pnl_ci_upper": float("nan"),
                    "total_realized_pnl": float("nan"),
                    "profit_rate": float("nan"),
                    "profit_rate_ci_lower": float("nan"),
                    "profit_rate_ci_upper": float("nan"),
                }
            )
            continue

        priced["_scenario_entry_price"] = pd.to_numeric(
            priced[entry_price_column],
            errors="coerce",
        )
        priced["_scenario_realized_pnl"] = (
            priced["spread_expiration_value"] - priced["_scenario_entry_price"] - TRANSACTION_COST
        )
        priced["_scenario_profit"] = priced["_scenario_realized_pnl"].gt(0).astype(float)

        mean_pnl, pnl_low, pnl_high, observation_count, cluster_count = _clustered_mean_ci(
            priced["_scenario_realized_pnl"],
            priced["required_outcome_key"],
        )
        mean_profit, profit_low, profit_high, _obs, _clusters = _clustered_mean_ci(
            priced["_scenario_profit"],
            priced["required_outcome_key"],
        )
        records.append(
            {
                "scenario_name": scenario_name,
                "entry_price_reference": entry_price_column,
                "priced_observation_count": observation_count,
                "outcome_cluster_count": cluster_count,
                "mean_entry_price": float(priced["_scenario_entry_price"].mean()),
                "mean_slippage_vs_quoted_debit": float(
                    (priced["_scenario_entry_price"] - priced["quoted_debit"]).mean()
                ),
                "mean_realized_pnl": mean_pnl,
                "mean_realized_pnl_ci_lower": pnl_low,
                "mean_realized_pnl_ci_upper": pnl_high,
                "total_realized_pnl": float(priced["_scenario_realized_pnl"].sum()),
                "profit_rate": mean_profit,
                "profit_rate_ci_lower": profit_low,
                "profit_rate_ci_upper": profit_high,
            }
        )

    return pd.DataFrame.from_records(records, columns=list(EXECUTION_SENSITIVITY_COLUMNS))


def _share_of_top(series: pd.Series, top_count: int) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").dropna().sort_values(ascending=False)
    total = float(cleaned.sum())
    if cleaned.empty or total <= 0:
        return float("nan")
    top_n = max(min(int(top_count), len(cleaned)), 0)
    if top_n == 0:
        return float("nan")
    return float(cleaned.iloc[:top_n].sum() / total)


def _winsorized_mean(series: pd.Series, percentile: float) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return float("nan")
    lower = float(cleaned.quantile(percentile))
    upper = float(cleaned.quantile(1.0 - percentile))
    return float(cleaned.clip(lower=lower, upper=upper).mean())


def _build_tail_concentration(observations: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for metric_name in ("realized_pnl_executable", "realized_pnl_quoted"):
        metric = pd.to_numeric(observations[metric_name], errors="coerce").dropna()
        positive = metric.loc[metric > 0].sort_values(ascending=False)
        absolute = metric.abs().sort_values(ascending=False)
        negative_total = float(metric.loc[metric < 0].sum())
        top_10pct_count = max(int(math.ceil(len(metric) * 0.10)), 1) if len(metric) else 0

        records.append(
            {
                "metric_name": metric_name,
                "observation_count": int(len(metric)),
                "positive_pnl_total": float(positive.sum()),
                "negative_pnl_total": negative_total,
                "max_winner": float(metric.max()) if not metric.empty else float("nan"),
                "max_loser": float(metric.min()) if not metric.empty else float("nan"),
                "top_1_positive_pnl_share": _share_of_top(positive, 1),
                "top_5_positive_pnl_share": _share_of_top(positive, 5),
                "top_10pct_positive_pnl_share": _share_of_top(positive, top_10pct_count),
                "top_1_abs_pnl_share": _share_of_top(absolute, 1),
                "top_5_abs_pnl_share": _share_of_top(absolute, 5),
                "top_10pct_abs_pnl_share": _share_of_top(absolute, top_10pct_count),
                "winsorized_mean_5pct": _winsorized_mean(metric, 0.05),
                "winsorized_mean_10pct": _winsorized_mean(metric, 0.10),
            }
        )

    return pd.DataFrame.from_records(records, columns=list(TAIL_CONCENTRATION_COLUMNS))


def _top_bottom_differences(
    metric_buckets: pd.DataFrame,
    *,
    metric_name: str,
) -> tuple[float, float]:
    metric_rows = metric_buckets.loc[metric_buckets["metric_name"] == metric_name].copy()
    if len(metric_rows) < 2:
        return float("nan"), float("nan")

    metric_rows = metric_rows.sort_values("bucket_index", kind="stable")
    top_row = metric_rows.iloc[0]
    bottom_row = metric_rows.iloc[-1]
    return (
        float(top_row["mean_realized_pnl_executable"] - bottom_row["mean_realized_pnl_executable"]),
        float(top_row["realized_profit_rate_executable"] - bottom_row["realized_profit_rate_executable"]),
    )


def build_effectiveness_report(
    summary: pd.DataFrame,
    exclusions: pd.DataFrame,
    exclusion_summary: pd.DataFrame,
    metric_buckets: pd.DataFrame,
    calibration_summary: pd.DataFrame,
    execution_sensitivity: pd.DataFrame,
    tail_concentration: pd.DataFrame,
) -> str:
    """Render one concise markdown effectiveness report."""
    if summary.empty:
        return "# Historical Effectiveness Report\n\nNo evaluation rows were produced.\n"

    summary_row = summary.iloc[0]
    calibration_row = calibration_summary.iloc[0] if not calibration_summary.empty else None
    ranking_rows = metric_buckets.loc[metric_buckets["metric_name"] == "ranking_score"].copy()
    ev_rows = metric_buckets.loc[metric_buckets["metric_name"] == "expected_value"].copy()
    baseline_execution = execution_sensitivity.loc[
        execution_sensitivity["scenario_name"] == "baseline_executable"
    ]
    quoted_execution = execution_sensitivity.loc[
        execution_sensitivity["scenario_name"] == "quoted_mid"
    ]
    ask_execution = execution_sensitivity.loc[
        execution_sensitivity["scenario_name"] == "displayed_ask"
    ]
    tail_row = tail_concentration.loc[
        tail_concentration["metric_name"] == "realized_pnl_executable"
    ]
    excluded_count = int(summary_row["excluded_opportunity_count"])
    missing_date_rows = exclusion_summary.loc[
        exclusion_summary["exclusion_reason"] == "missing_realized_underlying"
    ].copy()
    future_rows = exclusion_summary.loc[
        exclusion_summary["exclusion_reason"] == "realized_outcome_not_yet_available_as_of_cutoff"
    ].copy()

    lines = [
        "# Historical Effectiveness Report",
        "",
        "## Overall",
        (
            f"- historical opportunities generated: {int(summary_row['input_opportunity_count'])}"
        ),
        (
            f"- evaluable opportunities: {int(summary_row['evaluated_opportunity_count'])}; "
            f"excluded opportunities: {excluded_count}; "
            f"evaluation coverage: {summary_row['evaluation_coverage_rate']:.4f}"
        ),
        (
            f"- realized outcome groups: {int(summary_row['evaluated_outcome_count'])} "
            f"(shared outcome keys: {int(summary_row['shared_outcome_key_count'])})"
        ),
        (
            f"- evaluation status: {summary_row['evaluation_status']}"
        ),
        (
            f"- mean expected value: {summary_row['mean_expected_value']:.4f}; "
            f"mean realized PnL at executable entry: {summary_row['mean_realized_pnl_executable']:.4f}"
        ),
        (
            f"- total expected value: {summary_row['total_expected_value']:.4f}; "
            f"total realized PnL at executable entry: {summary_row['total_realized_pnl_executable']:.4f}"
        ),
        (
            f"- realized profit rate at executable entry: "
            f"{summary_row['realized_profit_rate_executable']:.4f} "
            f"[{summary_row['realized_profit_rate_ci_lower']:.4f}, "
            f"{summary_row['realized_profit_rate_ci_upper']:.4f}]"
        ),
        (
            f"- ranking-score discrimination: AUC vs realized profitable PnL="
            f"{summary_row['ranking_score_auc_realized_profit']:.4f}, "
            f"Spearman vs realized PnL={summary_row['ranking_score_spearman_realized_pnl']:.4f}"
        ),
        "",
        "## Exclusions",
    ]

    if exclusions.empty:
        lines.append("- no opportunities were excluded for missing realized outcomes")
    else:
        lines.append(
            (
                f"- excluded opportunities: {excluded_count} "
                f"({summary_row['excluded_opportunity_rate']:.4f} of generated opportunities)"
            )
        )
        if float(summary_row["evaluation_coverage_rate"]) < 0.95:
            lines.append(
                "- WARNING: material sample loss from unavailable realized outcomes; interpret effectiveness metrics cautiously."
            )
        if summary_row["missing_realized_event_dates"]:
            lines.append(
                f"- exact missing realized dates: {summary_row['missing_realized_event_dates']}"
            )
        if not missing_date_rows.empty:
            for row in missing_date_rows.to_dict("records"):
                lines.append(
                    (
                        f"- missing realized underlying on {row['required_event_date']}: "
                        f"{int(row['excluded_opportunity_count'])} excluded opportunities "
                        f"(spread types: {row['affected_spread_types'] or 'unknown'})"
                    )
                )
        if not future_rows.empty:
            for row in future_rows.to_dict("records"):
                lines.append(
                    (
                        f"- outcome not yet realized as of cutoff for {row['required_event_date']}: "
                        f"{int(row['excluded_opportunity_count'])} excluded opportunities"
                    )
                )

    if int(summary_row["evaluated_opportunity_count"]) == 0:
        lines.extend(["", "## Buckets"])
        lines.append("- no evaluable opportunities had realized outcomes; bucket analysis was not computed")
        lines.extend(["", "## Calibration", "- no evaluable opportunities had realized outcomes; calibration was not computed"])
        lines.extend(
            [
                "",
                "## Execution Sensitivity",
                "- no evaluable opportunities had realized outcomes; execution sensitivity was not computed",
                "",
                "## Tail Concentration",
                "- no evaluable opportunities had realized outcomes; tail concentration was not computed",
                "",
                "## Limitations",
                "- The study measures hold-to-expiration economics only; it is not a lifecycle option backtest.",
                "- Entry economics use the repo's existing quoted-mid, executable-debit, and displayed-ask references rather than historical fill records.",
                "- Probability calibration and realized PnL are evaluated only where separate realized outcomes exist after the chosen cutoff.",
                "- Shared expiration outcome keys create cross-candidate dependence, so bucket and overall confidence intervals are cluster-based by outcome key and still remain research approximations.",
                "- The current explicit terminal outcome policy in this repo remains bounded to SPY expiration-close semantics unless additional policies are added later.",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "",
            "## Buckets",
        ]
    )
    if not ranking_rows.empty:
        top_row = ranking_rows.sort_values("bucket_index", kind="stable").iloc[0]
        bottom_row = ranking_rows.sort_values("bucket_index", kind="stable").iloc[-1]
        lines.append(
            (
                f"- ranking-score top bucket mean realized PnL: "
                f"{top_row['mean_realized_pnl_executable']:.4f} "
                f"vs bottom bucket {bottom_row['mean_realized_pnl_executable']:.4f}"
            )
        )
        lines.append(
            (
                f"- ranking-score top bucket profit rate: "
                f"{top_row['realized_profit_rate_executable']:.4f} "
                f"vs bottom bucket {bottom_row['realized_profit_rate_executable']:.4f}"
            )
        )
    if not ev_rows.empty:
        top_row = ev_rows.sort_values("bucket_index", kind="stable").iloc[0]
        bottom_row = ev_rows.sort_values("bucket_index", kind="stable").iloc[-1]
        lines.append(
            (
                f"- expected-value top bucket mean realized PnL: "
                f"{top_row['mean_realized_pnl_executable']:.4f} "
                f"vs bottom bucket {bottom_row['mean_realized_pnl_executable']:.4f}"
            )
        )

    lines.extend(["", "## Calibration"])
    if calibration_row is None:
        lines.append("- probability calibration summary was unavailable")
    else:
        lines.append(
            (
                f"- Brier score: {calibration_row['brier_score']:.6f}; "
                f"ECE: {calibration_row['expected_calibration_error']:.6f}; "
                f"mean predicted probability: {calibration_row['mean_predicted_probability']:.4f}; "
                f"observed event rate: {calibration_row['overall_event_rate']:.4f}"
            )
        )

    lines.extend(["", "## Execution Sensitivity"])
    if not quoted_execution.empty:
        row = quoted_execution.iloc[0]
        lines.append(
            (
                f"- quoted midpoint mean realized PnL: {row['mean_realized_pnl']:.4f} "
                f"(n={int(row['priced_observation_count'])})"
            )
        )
    if not baseline_execution.empty:
        row = baseline_execution.iloc[0]
        lines.append(
            (
                f"- baseline executable mean realized PnL: {row['mean_realized_pnl']:.4f} "
                f"(mean slippage vs quoted debit {row['mean_slippage_vs_quoted_debit']:.4f})"
            )
        )
    if not ask_execution.empty:
        row = ask_execution.iloc[0]
        lines.append(
            (
                f"- displayed ask mean realized PnL: {row['mean_realized_pnl']:.4f} "
                f"(priced rows {int(row['priced_observation_count'])})"
            )
        )

    lines.extend(["", "## Tail Concentration"])
    if not tail_row.empty:
        row = tail_row.iloc[0]
        lines.append(
            (
                f"- top 5 winning observations contributed "
                f"{row['top_5_positive_pnl_share']:.4f} of positive executable PnL"
            )
        )
        lines.append(
            (
                f"- 5% winsorized executable mean PnL: "
                f"{row['winsorized_mean_5pct']:.4f}"
            )
        )

    lines.extend(
        [
            "",
            "## Limitations",
            "- The study measures hold-to-expiration economics only; it is not a lifecycle option backtest.",
            "- Entry economics use the repo's existing quoted-mid, executable-debit, and displayed-ask references rather than historical fill records.",
            "- Probability calibration and realized PnL are evaluated only where separate realized outcomes exist after the chosen cutoff.",
            "- Shared expiration outcome keys create cross-candidate dependence, so bucket and overall confidence intervals are cluster-based by outcome key and still remain research approximations.",
            "- The current explicit terminal outcome policy in this repo remains bounded to SPY expiration-close semantics unless additional policies are added later.",
        ]
    )
    return "\n".join(lines) + "\n"


def evaluate_scanner_effectiveness(
    opportunities: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    metric_columns: Sequence[str] | None = None,
    bucket_count: int = 10,
    segment_columns: Sequence[str] | None = None,
    drop_missing_outcomes: bool = False,
    exclusion_details: pd.DataFrame | None = None,
    allow_shared_outcome_keys: bool = True,
) -> EffectivenessEvaluationArtifacts:
    """Evaluate scanner rankings, EV, and probabilities against realized outcomes."""
    if bucket_count <= 0:
        raise ValueError("bucket_count must be positive.")

    working = validate_effectiveness_opportunity_frame(opportunities)
    validated_outcomes = validate_realized_outcome_frame(outcomes)
    input_opportunity_count = int(len(working))

    predictions = export_scanner_probability_predictions(working)
    if len(predictions) != len(working):
        raise ValueError("Prediction export did not preserve row count.")

    working = working.copy()
    predictions = predictions.reset_index(drop=True)
    working["prediction_id"] = predictions["prediction_id"].values
    working["prediction_timestamp"] = pd.to_datetime(
        predictions["prediction_timestamp"],
        errors="coerce",
        utc=True,
    ).dt.tz_localize(None)
    working["required_outcome_key"] = predictions["required_outcome_key"].astype("string").values
    working["observation_group_id"] = predictions["observation_group_id"].astype("string").values
    working["predicted_probability"] = pd.to_numeric(
        predictions["predicted_probability"],
        errors="coerce",
    ).values

    normalized_exclusion_details = _normalize_exclusion_details(exclusion_details)
    available_outcome_keys = set(validated_outcomes["required_outcome_key"].astype("string").tolist())
    keep_mask = working["required_outcome_key"].astype("string").isin(available_outcome_keys)
    exclusions = _build_exclusion_frame(
        working.loc[~keep_mask].reset_index(drop=True),
        exclusion_details=normalized_exclusion_details,
    )
    exclusion_summary = _build_exclusion_summary(exclusions)

    if not drop_missing_outcomes and not exclusions.empty:
        raise ValueError(f"Missing realized outcomes for {int(len(exclusions))} opportunity rows.")

    if drop_missing_outcomes:
        working = working.loc[keep_mask].reset_index(drop=True)
        predictions = predictions.loc[keep_mask].reset_index(drop=True)

    if working.empty:
        calibration_summary, calibration_bins, calibration_observations = _empty_calibration_outputs()
        observations = pd.DataFrame(columns=list(EFFECTIVENESS_OBSERVATION_COLUMNS))
        metric_buckets = pd.DataFrame(columns=list(METRIC_BUCKET_COLUMNS))
        segment_summary = pd.DataFrame(columns=list(SEGMENT_SUMMARY_COLUMNS))
        execution_sensitivity = pd.DataFrame(columns=list(EXECUTION_SENSITIVITY_COLUMNS))
        tail_concentration = pd.DataFrame(columns=list(TAIL_CONCENTRATION_COLUMNS))
        calibration_summary_row = None
        overall_summary = {
            "mean_predicted_probability": float("nan"),
            "observed_event_rate": float("nan"),
            "observed_event_rate_ci_lower": float("nan"),
            "observed_event_rate_ci_upper": float("nan"),
            "realized_profit_rate_executable": float("nan"),
            "realized_profit_rate_ci_lower": float("nan"),
            "realized_profit_rate_ci_upper": float("nan"),
            "mean_expected_value": float("nan"),
            "mean_realized_pnl_executable": float("nan"),
            "mean_realized_pnl_executable_ci_lower": float("nan"),
            "mean_realized_pnl_executable_ci_upper": float("nan"),
            "mean_realized_pnl_quoted": float("nan"),
            "total_expected_value": 0.0,
            "total_realized_pnl_executable": 0.0,
            "total_realized_pnl_quoted": 0.0,
        }
        ranking_top_bottom_pnl = float("nan")
        ranking_top_bottom_profit = float("nan")
        ev_top_bottom_pnl = float("nan")
        ev_top_bottom_profit = float("nan")
    else:
        calibration_artifacts = evaluate_probability_predictions(
            predictions,
            validated_outcomes,
            allow_shared_outcome_keys=allow_shared_outcome_keys,
        )
        calibration_summary = calibration_artifacts.summary.reset_index(drop=True)
        calibration_bins = calibration_artifacts.reliability_bins.reset_index(drop=True)
        calibration_observations = calibration_artifacts.observations.reset_index(drop=True)

        observations = working.merge(
            validated_outcomes,
            on="required_outcome_key",
            how="left",
            suffixes=("", "_outcome"),
            validate="many_to_one",
        )
        if observations["outcome_id"].isna().any():
            missing_count = int(observations["outcome_id"].isna().sum())
            raise ValueError(f"Missing realized outcomes for {missing_count} opportunity rows.")
        if not observations["ticker"].eq(observations["ticker_outcome"]).all():
            raise ValueError("Scanner opportunity / realized outcome ticker mismatch detected.")
        if not observations["expiration"].eq(observations["expiration_outcome"]).all():
            raise ValueError("Scanner opportunity / realized outcome expiration mismatch detected.")
        if not observations["realized_outcome_observed_at"].gt(observations["prediction_timestamp"]).all():
            raise ValueError("realized_outcome_observed_at must be strictly later than prediction_timestamp.")

        observations["realized_event"] = observations.apply(_compute_realized_event, axis=1).astype(int)
        observations["spread_expiration_value"] = observations.apply(_compute_expiration_value, axis=1).astype(float)
        observations["realized_pnl_quoted_gross"] = (
            observations["spread_expiration_value"] - observations["quoted_debit"]
        ).astype(float)
        observations["realized_pnl_quoted"] = (
            observations["realized_pnl_quoted_gross"] - TRANSACTION_COST
        ).astype(float)
        observations["realized_pnl_executable_gross"] = (
            observations["spread_expiration_value"] - observations["debit"]
        ).astype(float)
        observations["realized_pnl_executable"] = (
            observations["realized_pnl_executable_gross"] - TRANSACTION_COST
        ).astype(float)
        observations["realized_pnl_ask_gross"] = (
            observations["spread_expiration_value"] - observations["spread_ask"]
        ).astype(float)
        observations["realized_pnl_ask"] = (
            observations["realized_pnl_ask_gross"] - TRANSACTION_COST
        ).astype(float)
        observations["realized_positive_pnl_quoted"] = observations["realized_pnl_quoted"].gt(0).astype(int)
        observations["realized_positive_pnl_executable"] = observations["realized_pnl_executable"].gt(0).astype(int)
        observations["realized_positive_pnl_ask"] = observations["realized_pnl_ask"].gt(0).fillna(False).astype(int)
        observations["realized_return_on_risk_executable"] = (
            observations["realized_pnl_executable"] / observations["max_loss"]
        ).astype(float)
        observations["expected_minus_realized_pnl_executable"] = (
            observations["expected_value"] - observations["realized_pnl_executable"]
        ).astype(float)
        observations["breakeven_moneyness_pct"] = (
            (observations["predicted_event_threshold"] - observations["underlying_price"]).abs()
            / observations["underlying_price"]
        ).astype(float)
        observations["spread_market_width_pct"] = (
            observations["spread_market_width"] / observations["quoted_debit"]
        ).astype(float)
        observations["dte_bucket"] = _fixed_bucket_labels(
            observations["days_to_expiration"],
            bins=[-float("inf"), 7.0, 14.0, 30.0, 60.0, float("inf")],
            labels=["<=7", "8-14", "15-30", "31-60", ">60"],
        )
        observations["breakeven_moneyness_bucket"] = _fixed_bucket_labels(
            observations["breakeven_moneyness_pct"],
            bins=[-float("inf"), 0.02, 0.05, 0.10, float("inf")],
            labels=["<=2%", "2-5%", "5-10%", ">10%"],
        )
        observations["liquidity_bucket"] = _fixed_bucket_labels(
            observations["liquidity_score"],
            bins=[-float("inf"), 0.25, 0.50, 0.75, float("inf")],
            labels=["<=0.25", "0.25-0.50", "0.50-0.75", ">0.75"],
        )
        observations["spread_width_bucket"] = _fixed_bucket_labels(
            observations["spread_market_width_pct"],
            bins=[-float("inf"), 0.10, 0.25, 0.50, float("inf")],
            labels=["<=10%", "10-25%", "25-50%", ">50%"],
        )
        observations["volatility_regime_bucket"] = _fixed_bucket_labels(
            observations["implied_volatility"],
            bins=[-float("inf"), 0.15, 0.25, 0.40, float("inf")],
            labels=["<=15%", "15-25%", "25-40%", ">40%"],
        )
        observations["prediction_quarter"] = observations["prediction_timestamp"].map(_prediction_quarter_label)

        metric_names = tuple(metric_columns or _DEFAULT_METRIC_COLUMNS)
        for metric_name in metric_names:
            if metric_name not in observations.columns:
                raise ValueError(f"Requested metric column is unavailable for effectiveness study: {metric_name}")

        metric_bucket_frames = [
            _build_metric_bucket_summary(
                observations,
                metric_name=metric_name,
                bucket_count=bucket_count,
            )
            for metric_name in metric_names
        ]
        metric_buckets = (
            pd.concat(metric_bucket_frames, ignore_index=True)
            if metric_bucket_frames
            else pd.DataFrame(columns=list(METRIC_BUCKET_COLUMNS))
        )

        segment_summary = _build_segment_summary(
            observations,
            segment_columns=tuple(segment_columns or _DEFAULT_SEGMENT_COLUMNS),
        )
        execution_sensitivity = _build_execution_sensitivity(observations)
        tail_concentration = _build_tail_concentration(observations)

        overall_summary = _summarize_group(observations)
        ranking_top_bottom_pnl, ranking_top_bottom_profit = _top_bottom_differences(
            metric_buckets,
            metric_name="ranking_score",
        )
        ev_top_bottom_pnl, ev_top_bottom_profit = _top_bottom_differences(
            metric_buckets,
            metric_name="expected_value",
        )
        calibration_summary_row = (
            calibration_summary.iloc[0] if not calibration_summary.empty else None
        )

    excluded_opportunity_count = int(len(exclusions))
    missing_reason_mask = exclusions["exclusion_reason"].astype("string").isin(
        ["missing_realized_outcome", "missing_realized_underlying"]
    ) if not exclusions.empty else pd.Series([], dtype=bool)
    missing_realized_underlying_mask = exclusions["exclusion_reason"].astype("string").eq(
        "missing_realized_underlying"
    ) if not exclusions.empty else pd.Series([], dtype=bool)
    future_outcome_mask = exclusions["exclusion_reason"].astype("string").eq(
        "realized_outcome_not_yet_available_as_of_cutoff"
    ) if not exclusions.empty else pd.Series([], dtype=bool)
    missing_realized_event_dates = sorted(
        {
            str(value)
            for value in exclusion_summary.loc[
                exclusion_summary["exclusion_reason"].isin(
                    ["missing_realized_outcome", "missing_realized_underlying"]
                ),
                "required_event_date",
            ].dropna().tolist()
            if str(value) and str(value) != "unknown"
        }
    ) if not exclusion_summary.empty else []
    evaluated_opportunity_count = int(len(observations))
    evaluation_coverage_rate = float(evaluated_opportunity_count / input_opportunity_count)
    if observations.empty:
        ranking_score_spearman_realized_pnl = float("nan")
        ranking_score_spearman_realized_event = float("nan")
        expected_value_spearman_realized_pnl = float("nan")
        probability_spearman_realized_event = float("nan")
        ranking_score_auc_realized_event = float("nan")
        ranking_score_auc_realized_profit = float("nan")
        expected_value_auc_realized_profit = float("nan")
        probability_auc_realized_event = float("nan")
    else:
        ranking_score_spearman_realized_pnl = _safe_spearman(
            observations["ranking_score"],
            observations["realized_pnl_executable"],
        )
        ranking_score_spearman_realized_event = _safe_spearman(
            observations["ranking_score"],
            observations["realized_event"],
        )
        expected_value_spearman_realized_pnl = _safe_spearman(
            observations["expected_value"],
            observations["realized_pnl_executable"],
        )
        probability_spearman_realized_event = _safe_spearman(
            observations["predicted_probability"],
            observations["realized_event"],
        )
        ranking_score_auc_realized_event = _binary_auc(
            observations["ranking_score"],
            observations["realized_event"],
        )
        ranking_score_auc_realized_profit = _binary_auc(
            observations["ranking_score"],
            observations["realized_positive_pnl_executable"],
        )
        expected_value_auc_realized_profit = _binary_auc(
            observations["expected_value"],
            observations["realized_positive_pnl_executable"],
        )
        probability_auc_realized_event = _binary_auc(
            observations["predicted_probability"],
            observations["realized_event"],
        )

    summary = pd.DataFrame(
        [
            {
                "input_opportunity_count": input_opportunity_count,
                "evaluated_opportunity_count": evaluated_opportunity_count,
                "excluded_opportunity_count": excluded_opportunity_count,
                "evaluation_coverage_rate": evaluation_coverage_rate,
                "excluded_opportunity_rate": float(excluded_opportunity_count / input_opportunity_count),
                "excluded_missing_outcome_count": int(missing_reason_mask.sum()) if not exclusions.empty else 0,
                "excluded_missing_realized_underlying_count": (
                    int(missing_realized_underlying_mask.sum()) if not exclusions.empty else 0
                ),
                "excluded_future_outcome_count": (
                    int(future_outcome_mask.sum()) if not exclusions.empty else 0
                ),
                "missing_realized_event_date_count": int(len(missing_realized_event_dates)),
                "missing_realized_event_dates": ", ".join(missing_realized_event_dates),
                "available_outcome_count": int(len(validated_outcomes)),
                "evaluated_outcome_count": (
                    int(observations["required_outcome_key"].nunique()) if not observations.empty else 0
                ),
                "shared_outcome_key_count": (
                    int(calibration_summary_row["shared_outcome_key_count"])
                    if calibration_summary_row is not None
                    else (
                        int((observations["required_outcome_key"].value_counts() > 1).sum())
                        if not observations.empty
                        else 0
                    )
                ),
                "evaluation_status": (
                    "complete" if evaluated_opportunity_count > 0 else "insufficient_realized_outcome_data"
                ),
                "mean_predicted_probability": overall_summary["mean_predicted_probability"],
                "observed_event_rate": overall_summary["observed_event_rate"],
                "observed_event_rate_ci_lower": overall_summary["observed_event_rate_ci_lower"],
                "observed_event_rate_ci_upper": overall_summary["observed_event_rate_ci_upper"],
                "realized_profit_rate_executable": overall_summary["realized_profit_rate_executable"],
                "realized_profit_rate_ci_lower": overall_summary["realized_profit_rate_ci_lower"],
                "realized_profit_rate_ci_upper": overall_summary["realized_profit_rate_ci_upper"],
                "mean_expected_value": overall_summary["mean_expected_value"],
                "mean_realized_pnl_executable": overall_summary["mean_realized_pnl_executable"],
                "mean_realized_pnl_executable_ci_lower": overall_summary["mean_realized_pnl_executable_ci_lower"],
                "mean_realized_pnl_executable_ci_upper": overall_summary["mean_realized_pnl_executable_ci_upper"],
                "mean_realized_pnl_quoted": overall_summary["mean_realized_pnl_quoted"],
                "total_expected_value": overall_summary["total_expected_value"],
                "total_realized_pnl_executable": overall_summary["total_realized_pnl_executable"],
                "total_realized_pnl_quoted": overall_summary["total_realized_pnl_quoted"],
                "ranking_score_spearman_realized_pnl": ranking_score_spearman_realized_pnl,
                "ranking_score_spearman_realized_event": ranking_score_spearman_realized_event,
                "expected_value_spearman_realized_pnl": expected_value_spearman_realized_pnl,
                "probability_spearman_realized_event": probability_spearman_realized_event,
                "ranking_score_auc_realized_event": ranking_score_auc_realized_event,
                "ranking_score_auc_realized_profit": ranking_score_auc_realized_profit,
                "expected_value_auc_realized_profit": expected_value_auc_realized_profit,
                "probability_auc_realized_event": probability_auc_realized_event,
                "ranking_score_top_minus_bottom_mean_realized_pnl": ranking_top_bottom_pnl,
                "ranking_score_top_minus_bottom_profit_rate": ranking_top_bottom_profit,
                "expected_value_top_minus_bottom_mean_realized_pnl": ev_top_bottom_pnl,
                "expected_value_top_minus_bottom_profit_rate": ev_top_bottom_profit,
            }
        ],
        columns=list(EFFECTIVENESS_SUMMARY_COLUMNS),
    )

    if observations.empty:
        serialized_observations = observations.copy()
    else:
        serialized_observations = observations.sort_values(
            by=["prediction_timestamp", "prediction_id"],
            kind="stable",
        ).reset_index(drop=True)
        for column in EFFECTIVENESS_OBSERVATION_COLUMNS:
            if column not in serialized_observations.columns:
                serialized_observations[column] = pd.NA
        serialized_observations = serialized_observations.loc[:, list(EFFECTIVENESS_OBSERVATION_COLUMNS)]

    report_markdown = build_effectiveness_report(
        summary,
        exclusions,
        exclusion_summary,
        metric_buckets,
        calibration_summary,
        execution_sensitivity,
        tail_concentration,
    )
    return EffectivenessEvaluationArtifacts(
        predictions=predictions.reset_index(drop=True),
        calibration_summary=calibration_summary,
        calibration_bins=calibration_bins,
        calibration_observations=calibration_observations,
        observations=serialized_observations,
        exclusions=exclusions.reset_index(drop=True),
        exclusion_summary=exclusion_summary.reset_index(drop=True),
        summary=summary,
        metric_buckets=metric_buckets.reset_index(drop=True),
        segment_summary=segment_summary.reset_index(drop=True),
        execution_sensitivity=execution_sensitivity.reset_index(drop=True),
        tail_concentration=tail_concentration.reset_index(drop=True),
        report_markdown=report_markdown,
    )
