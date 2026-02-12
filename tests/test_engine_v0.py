import unittest
from datetime import date

from packages.engine.v0 import EngineInput, run_engine_v0


def synthetic_returns(months: int = 60):
    data = {}
    tickers = ["SPY", "QQQ", "IEF", "SHY", "VNQ"]
    y, m = 2020, 1
    for t in tickers:
        rows = []
        yy, mm = y, m
        for i in range(months):
            d = date(yy, mm, 28).isoformat()
            if t in {"SPY", "QQQ"}:
                r = 0.006 + (0.001 if i % 2 == 0 else -0.001)
            elif t in {"IEF", "SHY"}:
                r = 0.002 + (0.0005 if i % 3 == 0 else -0.0003)
            else:
                r = 0.003 + (0.002 if i % 4 == 0 else -0.001)
            rows.append((d, r))
            mm += 1
            if mm > 12:
                mm = 1
                yy += 1
        data[t] = rows
    return data


def base_input(**kwargs):
    payload = {
        "current_balance_krw": 10_000_000,
        "monthly_contribution_krw": 500_000,
        "start_date": "2025-01-01",
        "retirement_date": "2030-01-01",
        "target_cagr": 6.0,
        "max_mdd": 20.0,
    }
    payload.update(kwargs)
    return EngineInput(**payload)


class EngineV0Tests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        result = run_engine_v0(base_input(), returns_by_ticker=synthetic_returns())
        self.assertAlmostEqual(sum(p["weight"] for p in result["portfolio"]), 1.0, places=4)

    def test_mdd_constraint_respected_or_warning_present(self):
        max_mdd = 15.0
        result = run_engine_v0(base_input(max_mdd=max_mdd), returns_by_ticker=synthetic_returns())
        est_mdd = result["metrics"]["est_mdd"]
        warns = " ".join(result["warnings"])
        self.assertTrue(est_mdd <= (max_mdd / 100.0) or "No portfolio met max_mdd constraint" in warns)

    def test_accumulation_monotonic_with_positive_contribution(self):
        result = run_engine_v0(
            base_input(current_balance_krw=1_000_000, monthly_contribution_krw=300_000, retirement_date="2026-01-01", target_cagr=5.0),
            returns_by_ticker=synthetic_returns(),
        )
        balances = [row["balance"] for row in result["accumulation_series"]]
        self.assertTrue(all(b2 >= b1 for b1, b2 in zip(balances, balances[1:])))

    def test_decum_target_years_has_expected_duration(self):
        result = run_engine_v0(base_input(withdrawal_mode="target_years", target_years=15), returns_by_ticker=synthetic_returns())
        self.assertEqual(result["retirement_summary"]["duration_months"], 180)
        self.assertEqual(len(result["retirement_series"]), 180)

    def test_decum_target_years_near_zero_rm(self):
        result = run_engine_v0(
            base_input(target_cagr=1.4, fee_annual=0.004, retirement_return_haircut_pct=1.0, retirement_fee_annual=0.004),
            returns_by_ticker=synthetic_returns(),
        )
        self.assertGreater(result["retirement_summary"]["monthly_withdrawal"], 0)

    def test_decum_fixed_monthly_depletion_warning(self):
        result = run_engine_v0(
            base_input(withdrawal_mode="fixed_monthly", fixed_monthly_withdrawal_krw=50_000_000),
            returns_by_ticker=synthetic_returns(),
        )
        self.assertLessEqual(result["retirement_summary"]["duration_months"], 12)
        self.assertTrue(any("depletes within 12 months" in w for w in result["warnings"]))

    def test_decum_fixed_monthly_runs_with_valid_input(self):
        result = run_engine_v0(
            base_input(withdrawal_mode="fixed_monthly", fixed_monthly_withdrawal_krw=1_000_000),
            returns_by_ticker=synthetic_returns(),
        )
        self.assertGreater(len(result["retirement_series"]), 0)
        self.assertGreater(result["retirement_summary"]["monthly_withdrawal"], 0)


if __name__ == "__main__":
    unittest.main()
