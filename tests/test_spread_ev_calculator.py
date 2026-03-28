import math
import unittest

from options_edge_scanner.models.spread_ev_calculator import TRANSACTION_COST, calculate_expected_value


class SpreadEVCalculatorTests(unittest.TestCase):
    def test_bull_call_debit_breakeven_binary_ev(self) -> None:
        spread = {
            "spread_type": "bull_call_debit",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 3,
            "max_profit": 7,
        }
        probabilities = {"win": 0.6, "loss": 0.4}

        result = calculate_expected_value(spread, probability_weights=probabilities)

        expected_gross = (0.6 * 7) + (0.4 * -3)
        expected = expected_gross - TRANSACTION_COST
        self.assertAlmostEqual(result["expected_value"], expected, places=10)
        self.assertEqual(result["ev_method"], "breakeven_binary_mvp")
        self.assertEqual(result["prob_win"], 0.6)
        self.assertEqual(result["prob_loss"], 0.4)

    def test_bear_call_credit_breakeven_binary_ev(self) -> None:
        spread = {
            "spread_type": "bear_call_credit",
            "short_strike": 110,
            "long_strike": 100,
            "credit": 2,
            "max_loss": 8,
        }
        probabilities = {"probability_of_profit": 0.7, "probability_of_loss": 0.3}

        result = calculate_expected_value(spread, probability_weights=probabilities)

        expected_gross = (0.7 * 2) + (0.3 * -8)
        expected = expected_gross - TRANSACTION_COST
        self.assertAlmostEqual(result["expected_value"], expected, places=10)

    def test_supported_spread_accepts_scalar_probability(self) -> None:
        spread = {
            "spread_type": "bull_call_debit",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 3,
            "max_profit": 7,
        }

        result = calculate_expected_value(spread, probability=0.6)

        expected_gross = (0.6 * 7) + (0.4 * -3)
        expected = expected_gross - TRANSACTION_COST
        self.assertAlmostEqual(result["expected_value"], expected, places=10)
        self.assertEqual(result["ev_method"], "breakeven_binary_mvp")
        self.assertEqual(result["prob_win"], 0.6)
        self.assertEqual(result["prob_loss"], 0.4)

    def test_breakeven_binary_ev_is_bound_by_max_profit_and_loss_before_cost(self) -> None:
        spread = {
            "spread_type": "bull_put_credit",
            "short_strike": 110,
            "long_strike": 100,
            "credit": 2,
            "max_loss": 8,
        }
        result = calculate_expected_value(
            spread,
            probability_weights={"win": 1.0, "loss": 0.0},
        )
        self.assertLessEqual(result["expected_value"], 2 - TRANSACTION_COST + 1e-12)
        self.assertGreaterEqual(result["expected_value"], -8 - TRANSACTION_COST - 1e-12)

    def test_raises_on_invalid_probability_weights_sum(self) -> None:
        spread = {
            "spread_type": "bear_put_debit",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 3,
            "max_profit": 7,
        }
        with self.assertRaises(ValueError):
            calculate_expected_value(
                spread,
                probability_weights={"win": 0.8, "loss": 0.3},
            )

    def test_raises_on_unrecognized_spread_type(self) -> None:
        spread = {
            "spread_type": "call_vertical",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 3,
            "max_profit": 7,
        }
        with self.assertRaises(ValueError):
            calculate_expected_value(
                spread,
                probability_weights={"win": 0.5, "loss": 0.5},
            )

    def test_binary_fallback_compatibility(self) -> None:
        spread = {"payoff": 1.5, "loss": 3.0}
        result = calculate_expected_value(spread, probability=0.4)
        expected = (0.4 * 1.5) - (0.6 * 3.0) - TRANSACTION_COST
        self.assertTrue(math.isclose(result["expected_value"], expected))
        self.assertEqual(result["ev_method"], "binary")

    def test_raises_on_invalid_binary_probability(self) -> None:
        spread = {"payoff": 2.0, "loss": 1.0}
        with self.assertRaises(ValueError):
            calculate_expected_value(spread, probability=1.2)


if __name__ == "__main__":
    unittest.main()
