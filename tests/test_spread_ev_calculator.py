import math
import unittest

from options_edge_scanner.models.spread_ev_calculator import TRANSACTION_COST, calculate_expected_value


class SpreadEVCalculatorTests(unittest.TestCase):
    def test_call_debit_vertical_three_region_ev(self) -> None:
        spread = {
            "spread_type": "call_vertical",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 3,
            "max_profit": 7,
        }
        weights = {"below": 0.2, "between": 0.3, "above": 0.5}

        result = calculate_expected_value(spread, probability_weights=weights)

        # Region PnL: below=-3, between=(10/2-3)=2, above=7
        expected = (0.2 * -3) + (0.3 * 2) + (0.5 * 7) - TRANSACTION_COST
        self.assertAlmostEqual(result["expected_value"], expected, places=10)
        self.assertEqual(result["ev_method"], "three_region_midpoint")

    def test_put_credit_vertical_three_region_ev(self) -> None:
        spread = {
            "spread_type": "put_credit",
            "short_strike": 110,
            "long_strike": 100,
            "credit": 2,
            "max_loss": 8,
        }
        weights = {"below": 0.1, "between": 0.2, "above": 0.7}

        result = calculate_expected_value(spread, probability_weights=weights)

        # Region PnL: below=-8, between=(2-10/2)=-3, above=2
        expected = (0.1 * -8) + (0.2 * -3) + (0.7 * 2) - TRANSACTION_COST
        self.assertAlmostEqual(result["expected_value"], expected, places=10)

    def test_three_region_ev_is_bound_by_max_profit_and_loss(self) -> None:
        spread = {
            "spread_type": "call_vertical",
            "strike_lower": 100,
            "strike_upper": 110,
            "cost": 4,
            "max_profit": 6,
        }
        result = calculate_expected_value(
            spread,
            probability_weights={"below": 0.0, "between": 0.0, "above": 1.0},
        )
        self.assertLessEqual(result["expected_value"], 6 - TRANSACTION_COST + 1e-12)
        self.assertGreaterEqual(result["expected_value"], -4 - TRANSACTION_COST - 1e-12)

    def test_binary_fallback_compatibility(self) -> None:
        spread = {"payoff": 1.5, "loss": 3.0}
        result = calculate_expected_value(spread, probability=0.4)
        expected = (0.4 * 1.5) - (0.6 * 3.0) - TRANSACTION_COST
        self.assertTrue(math.isclose(result["expected_value"], expected))
        self.assertEqual(result["ev_method"], "binary")


if __name__ == "__main__":
    unittest.main()
