from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from options_edge_scanner.calibration import (
    build_observation_group_id,
    build_expanding_windows,
    build_fixed_holdout_window,
    build_reliability_bins,
    build_required_outcome_key,
    build_rolling_windows,
    evaluate_probability_predictions,
    export_scanner_probability_predictions,
    join_predictions_with_realized_outcomes,
    validate_probability_prediction_frame,
    validate_realized_outcome_frame,
)
from options_edge_scanner.data.loader import load_option_quotes
from options_edge_scanner.scanner.engine import build_scanner_opportunities


PREDICTION_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_probability_predictions.csv"
OUTCOME_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_realized_outcomes.csv"
OPTION_CHAIN_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_option_chain.csv"


def _load_prediction_fixture() -> pd.DataFrame:
    return pd.read_csv(PREDICTION_FIXTURE_PATH)


def _load_outcome_fixture() -> pd.DataFrame:
    return pd.read_csv(OUTCOME_FIXTURE_PATH)


def _refresh_prediction_contract_fields(predictions: pd.DataFrame, row_index: int) -> None:
    predictions.loc[row_index, "required_outcome_key"] = build_required_outcome_key(
        ticker=predictions.loc[row_index, "ticker"],
        expiration=predictions.loc[row_index, "expiration"],
        required_outcome_horizon=predictions.loc[row_index, "required_outcome_horizon"],
    )
    predictions.loc[row_index, "observation_group_id"] = build_observation_group_id(
        snapshot_id=predictions.loc[row_index, "snapshot_id"],
        ticker=predictions.loc[row_index, "ticker"],
        prediction_timestamp=predictions.loc[row_index, "prediction_timestamp"],
        expiration=predictions.loc[row_index, "expiration"],
    )


def _refresh_outcome_contract_fields(outcomes: pd.DataFrame, row_index: int) -> None:
    outcomes.loc[row_index, "required_outcome_key"] = build_required_outcome_key(
        ticker=outcomes.loc[row_index, "ticker"],
        expiration=outcomes.loc[row_index, "expiration"],
        required_outcome_horizon=outcomes.loc[row_index, "required_outcome_horizon"],
        realized_outcome_measure=outcomes.loc[row_index, "realized_outcome_measure"],
    )


def _make_prediction_records(
    probabilities: list[float],
    realized_events: list[int],
    *,
    base_timestamp: str = "2026-01-02T15:30:00Z",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prediction_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []

    base_ts = pd.Timestamp(base_timestamp)
    for index, (probability, realized_event) in enumerate(zip(probabilities, realized_events, strict=True), start=1):
        ticker = f"T{index:02d}"
        prediction_timestamp = (base_ts + pd.Timedelta(days=index - 1)).isoformat().replace("+00:00", "Z")
        expiration = (base_ts + pd.Timedelta(days=30 + index)).strftime("%Y-%m-%d")
        required_outcome_key = build_required_outcome_key(
            ticker=ticker,
            expiration=expiration,
            required_outcome_horizon="expiration",
        )
        threshold = 100.0
        terminal_price = 101.0 if realized_event else 99.0

        prediction_rows.append(
            {
                "prediction_id": f"pred_{index:03d}",
                "snapshot_id": f"snap_{index:03d}",
                "ticker": ticker,
                "prediction_timestamp": prediction_timestamp,
                "quote_observed_at": prediction_timestamp,
                "as_of": prediction_timestamp,
                "expiration": expiration,
                "spread_type": "bull_call_debit",
                "lower_strike": 95.0,
                "upper_strike": 105.0,
                "long_strike": 95.0,
                "short_strike": 105.0,
                "predicted_probability": probability,
                "probability_model_name": "lognormal_breakeven",
                "probability_model_version": "1",
                "predicted_event_name": "terminal_underlying_crosses_spread_breakeven",
                "predicted_event_direction": "above",
                "predicted_event_operator": ">",
                "predicted_event_threshold": threshold,
                "predicted_event_horizon": "expiration",
                "required_outcome_horizon": "expiration",
                "required_outcome_key": required_outcome_key,
                "observation_group_id": f"snap_{index:03d}|{ticker}|{prediction_timestamp}|{expiration}",
            }
        )
        outcome_rows.append(
            {
                "outcome_id": f"out_{index:03d}",
                "required_outcome_key": required_outcome_key,
                "ticker": ticker,
                "expiration": expiration,
                "required_outcome_horizon": "expiration",
                "realized_outcome_measure": "terminal_underlying_price",
                "realized_terminal_underlying_price": terminal_price,
                "realized_outcome_observed_at": (
                    pd.Timestamp(expiration).tz_localize("UTC") + pd.Timedelta(hours=20)
                ).isoformat().replace("+00:00", "Z"),
                "realized_outcome_source": "fixture.expiration",
            }
        )

    return pd.DataFrame(prediction_rows), pd.DataFrame(outcome_rows)


def test_probability_calibration_fixture_contracts_validate() -> None:
    predictions = validate_probability_prediction_frame(_load_prediction_fixture())
    outcomes = validate_realized_outcome_frame(_load_outcome_fixture())

    assert len(predictions) == 4
    assert len(outcomes) == 4
    assert predictions["prediction_id"].tolist()[0] == "pred_001"
    assert outcomes["outcome_id"].tolist()[-1] == "out_004"


def test_export_scanner_probability_predictions_preserves_model_event_provenance() -> None:
    option_quotes = load_option_quotes(OPTION_CHAIN_FIXTURE_PATH)
    opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")

    exported = export_scanner_probability_predictions(opportunities)

    assert not exported.empty
    assert set(exported["probability_model_name"]) == {"lognormal_breakeven"}
    assert set(exported["probability_model_version"]) == {"1"}
    assert set(exported["predicted_event_name"]) == {"terminal_underlying_crosses_spread_breakeven"}
    assert set(exported["predicted_event_direction"]) == {"above", "below"}
    assert set(exported["predicted_event_operator"]) == {">", "<"}
    assert exported["prediction_id"].is_unique
    assert exported["required_outcome_key"].str.contains("terminal_underlying_price").all()
    assert len(validate_probability_prediction_frame(exported)) == len(exported)


def test_export_scanner_probability_predictions_uses_later_as_of_for_prediction_timing() -> None:
    option_quotes = load_option_quotes(OPTION_CHAIN_FIXTURE_PATH)
    base_opportunities = build_scanner_opportunities(option_quotes, as_of="2026-01-02")
    opportunities = base_opportunities.copy()
    opportunities["as_of"] = opportunities["quote_observed_at"] + pd.Timedelta(days=1)

    base_exported = export_scanner_probability_predictions(base_opportunities)
    exported = export_scanner_probability_predictions(opportunities)

    assert exported["prediction_timestamp"].equals(exported["as_of"])
    assert not exported["prediction_timestamp"].equals(exported["quote_observed_at"])
    assert exported["prediction_id"].is_unique
    assert not exported["observation_group_id"].equals(base_exported["observation_group_id"])


def test_evaluate_probability_predictions_with_fixture_rows() -> None:
    artifacts = evaluate_probability_predictions(
        _load_prediction_fixture(),
        _load_outcome_fixture(),
        bin_count=4,
    )

    summary = artifacts.summary.iloc[0]
    assert len(artifacts.observations) == 4
    assert summary["prediction_count"] == 4
    assert summary["outcome_count"] == 4
    assert summary["overall_event_rate"] == pytest.approx(0.5)
    assert summary["mean_predicted_probability"] == pytest.approx(0.6125)
    assert summary["brier_score"] == pytest.approx(0.090625)
    assert artifacts.observations.loc[0, "snapshot_source"] == "fixture.snapshot"
    assert artifacts.observations.loc[0, "input_path"] == "fixtures/xyz_prediction.csv"
    assert (
        artifacts.observations.loc[0, "source_metadata_path"]
        == "fixtures/xyz_prediction.csv.meta.json"
    )
    assert "Calibration summary:" in artifacts.reliability_summary


def test_perfectly_calibrated_synthetic_predictions_have_zero_brier_and_zero_ece() -> None:
    predictions, outcomes = _make_prediction_records([0.0, 0.0, 1.0, 1.0], [0, 0, 1, 1])

    artifacts = evaluate_probability_predictions(predictions, outcomes, bin_count=2)
    summary = artifacts.summary.iloc[0]

    assert summary["brier_score"] == pytest.approx(0.0)
    assert summary["expected_calibration_error"] == pytest.approx(0.0)
    assert summary["maximum_calibration_error"] == pytest.approx(0.0)


def test_overconfident_predictions_have_worse_calibration_error_than_underconfident_predictions() -> None:
    overconfident_predictions, overconfident_outcomes = _make_prediction_records(
        [0.99, 0.99, 0.01, 0.01],
        [1, 0, 1, 0],
    )
    underconfident_predictions, underconfident_outcomes = _make_prediction_records(
        [0.55, 0.55, 0.45, 0.45],
        [1, 0, 1, 0],
    )

    overconfident = evaluate_probability_predictions(
        overconfident_predictions,
        overconfident_outcomes,
        bin_count=2,
    )
    underconfident = evaluate_probability_predictions(
        underconfident_predictions,
        underconfident_outcomes,
        bin_count=2,
    )

    assert (
        overconfident.summary.iloc[0]["expected_calibration_error"]
        > underconfident.summary.iloc[0]["expected_calibration_error"]
    )
    assert overconfident.summary.iloc[0]["brier_score"] > underconfident.summary.iloc[0]["brier_score"]


def test_constant_probability_baseline_has_expected_event_rate_and_brier() -> None:
    predictions, outcomes = _make_prediction_records([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1])

    artifacts = evaluate_probability_predictions(predictions, outcomes, bin_count=2)
    summary = artifacts.summary.iloc[0]

    assert summary["overall_event_rate"] == pytest.approx(0.5)
    assert summary["mean_predicted_probability"] == pytest.approx(0.5)
    assert summary["brier_score"] == pytest.approx(0.25)


def test_reliability_bins_include_empty_bins() -> None:
    predictions, outcomes = _make_prediction_records([0.1, 0.9], [0, 1])
    observations = join_predictions_with_realized_outcomes(predictions, outcomes)

    bins = build_reliability_bins(observations, bin_count=5)

    assert len(bins) == 5
    assert (bins["prediction_count"] == 0).sum() >= 1
    assert bins.loc[bins["prediction_count"] == 0, "observed_event_rate"].isna().all()


def test_log_loss_with_zero_and_one_probabilities_is_finite_due_to_safe_clipping() -> None:
    predictions, outcomes = _make_prediction_records([0.0, 1.0], [0, 1])

    artifacts = evaluate_probability_predictions(predictions, outcomes, bin_count=2)
    assert artifacts.summary.iloc[0]["log_loss"] >= 0.0
    assert pd.notna(artifacts.summary.iloc[0]["log_loss"])


def test_invalid_probability_outside_unit_interval_raises() -> None:
    predictions, outcomes = _make_prediction_records([0.5], [1])
    predictions.loc[0, "predicted_probability"] = 1.5

    with pytest.raises(ValueError, match="predicted_probability must be within \\[0, 1\\]"):
        evaluate_probability_predictions(predictions, outcomes)


def test_duplicate_prediction_ids_raise() -> None:
    predictions, outcomes = _make_prediction_records([0.5, 0.4], [1, 0])
    predictions.loc[1, "prediction_id"] = predictions.loc[0, "prediction_id"]

    with pytest.raises(ValueError, match="prediction_id values must be unique"):
        evaluate_probability_predictions(predictions, outcomes)


def test_mismatched_prediction_outcome_semantics_raise() -> None:
    predictions, outcomes = _make_prediction_records([0.5], [1])
    predictions.loc[0, "predicted_event_name"] = "unsupported.event"

    with pytest.raises(ValueError, match="Unsupported predicted_event_name"):
        evaluate_probability_predictions(predictions, outcomes)


def test_shared_outcome_keys_are_rejected_by_default_and_allowed_explicitly() -> None:
    predictions, outcomes = _make_prediction_records([0.6, 0.7], [1, 0])
    predictions.loc[1, "ticker"] = predictions.loc[0, "ticker"]
    predictions.loc[1, "expiration"] = predictions.loc[0, "expiration"]
    _refresh_prediction_contract_fields(predictions, 1)
    outcomes = outcomes.iloc[[0]].reset_index(drop=True)

    with pytest.raises(ValueError, match="Multiple predictions share the same required_outcome_key"):
        evaluate_probability_predictions(predictions, outcomes)

    artifacts = evaluate_probability_predictions(
        predictions,
        outcomes,
        allow_shared_outcome_keys=True,
    )
    assert len(artifacts.observations) == 2
    assert artifacts.summary.iloc[0]["shared_outcome_key_count"] == 1


def test_prediction_timestamp_must_be_on_or_after_as_of() -> None:
    predictions, outcomes = _make_prediction_records([0.5], [1])
    predictions.loc[0, "as_of"] = "2026-02-14T15:30:00Z"

    with pytest.raises(ValueError, match="prediction_timestamp must be on or after as_of"):
        evaluate_probability_predictions(predictions, outcomes)


def test_expiration_day_predictions_are_rejected_conservatively() -> None:
    predictions, _outcomes = _make_prediction_records([0.5], [1])
    predictions.loc[0, "prediction_timestamp"] = "2026-02-13T10:00:00Z"
    predictions.loc[0, "quote_observed_at"] = "2026-02-13T10:00:00Z"
    predictions.loc[0, "as_of"] = "2026-02-13T09:00:00Z"
    predictions.loc[0, "expiration"] = "2026-02-13"
    _refresh_prediction_contract_fields(predictions, 0)

    with pytest.raises(
        ValueError,
        match="expiration-horizon predictions must be observed before the expiration date",
    ):
        validate_probability_prediction_frame(predictions)


def test_required_outcome_key_must_match_prediction_fields() -> None:
    predictions, _outcomes = _make_prediction_records([0.5], [1])
    predictions.loc[0, "required_outcome_key"] = "WRONG|2026-02-02|expiration|terminal_underlying_price"

    with pytest.raises(ValueError, match="required_outcome_key does not match prediction contract fields"):
        validate_probability_prediction_frame(predictions)


def test_required_outcome_key_must_match_realized_outcome_fields() -> None:
    _predictions, outcomes = _make_prediction_records([0.5], [1])
    outcomes.loc[0, "required_outcome_key"] = "WRONG|2026-02-02|expiration|terminal_underlying_price"

    with pytest.raises(
        ValueError,
        match="required_outcome_key does not match realized outcome contract fields",
    ):
        validate_realized_outcome_frame(outcomes)


def test_missing_realized_outcomes_raise() -> None:
    predictions, outcomes = _make_prediction_records([0.5], [1])
    outcomes = outcomes.iloc[0:0].copy()

    with pytest.raises(ValueError, match="Missing realized outcomes for prediction_ids"):
        evaluate_probability_predictions(predictions, outcomes)


def test_joined_observations_are_deterministically_sorted() -> None:
    predictions = _load_prediction_fixture().sample(frac=1.0, random_state=7).reset_index(drop=True)
    outcomes = _load_outcome_fixture().sample(frac=1.0, random_state=11).reset_index(drop=True)

    observations = join_predictions_with_realized_outcomes(predictions, outcomes)

    assert observations["prediction_timestamp"].is_monotonic_increasing
    assert observations["prediction_id"].tolist() == ["pred_001", "pred_002", "pred_003", "pred_004"]


def test_forward_time_windows_are_strictly_forward_only() -> None:
    predictions = _load_prediction_fixture()

    holdout = build_fixed_holdout_window(predictions, holdout_start="2026-01-05T00:00:00Z")
    expanding = build_expanding_windows(predictions, min_train_size=2, test_size=1)
    rolling = build_rolling_windows(predictions, train_size=2, test_size=1)

    assert len(holdout) == 1
    assert holdout[0].train_end < holdout[0].test_start
    assert expanding[0].train_end < expanding[0].test_start
    assert rolling[0].train_end < rolling[0].test_start
