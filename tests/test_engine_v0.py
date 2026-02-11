import unittest
from datetime import date

from packages.engine.v0 import EngineInput, run_engine_v0


def synthetic_returns(months: int = 60):
    data = {}
    tickers = ["SPY", "QQQ", "IEF", "SHY", "VNQ"]
    start_year = 2020
    start_month = 1
    for t in tickers:
        rows = []
        y, m = start_year, start_month
        for i in range(months):
            d = date(y, m, 28).isoformat()
            if t in {"SPY", "QQQ"}:
                r = 0.006 + (0.001 if i % 2 == 0 else -0.001)
            elif t in {"IEF", "SHY"}:
                r = 0.002 + (0.0005 if i % 3 == 0 else -0.0003)
            else:
                r = 0.003 + (0.002 if i % 4 == 0 else -0.001)
            rows.append((d, r))
            m += 1
            if m > 12:
                m = 1
                y += 1
        data[t] = rows
    return data


class EngineV0Tests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        result = run_engine_v0(
            EngineInput(
                current_balance_krw=10_000_000,
                monthly_contribution_krw=500_000,
                start_date="2025-01-01",
                retirement_date="2030-01-01",
                target_cagr=6.0,
                max_mdd=20.0,
            ),
            returns_by_ticker=synthetic_returns(),
        )
        total_weight = sum(p["weight"] for p in result["portfolio"])
        self.assertAlmostEqual(total_weight, 1.0, places=4)

    def test_mdd_constraint_respected_or_warning_present(self):
        max_mdd = 15.0
        result = run_engine_v0(
            EngineInput(
                current_balance_krw=10_000_000,
                monthly_contribution_krw=500_000,
                start_date="2025-01-01",
                retirement_date="2031-01-01",
                target_cagr=7.0,
                max_mdd=max_mdd,
            ),
            returns_by_ticker=synthetic_returns(),
        )
        est_mdd = result["metrics"]["est_mdd"]
        warns = " ".join(result["warnings"])
        self.assertTrue(est_mdd <= (max_mdd / 100.0) or "No portfolio met max_mdd constraint" in warns)

    def test_accumulation_monotonic_with_positive_contribution(self):
        result = run_engine_v0(
            EngineInput(
                current_balance_krw=1_000_000,
                monthly_contribution_krw=300_000,
                start_date="2025-01-01",
                retirement_date="2026-01-01",
                target_cagr=5.0,
                max_mdd=25.0,
            ),
            returns_by_ticker=synthetic_returns(),
        )
        balances = [row["balance"] for row in result["accumulation_series"]]
        self.assertTrue(all(b2 >= b1 for b1, b2 in zip(balances, balances[1:])))


if __name__ == "__main__":
    unittest.main()
