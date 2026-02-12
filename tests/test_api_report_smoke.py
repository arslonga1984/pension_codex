import importlib.util
import unittest


class ApiReportSmokeTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("pydantic"), "fastapi/pydantic not installed")
    def test_report_returns_pdf_content_type(self):
        from fastapi.testclient import TestClient

        import apps.api.main as api_main

        client = TestClient(api_main.app)

        # Avoid filesystem/dependency coupling in this smoke test.
        original_ensure = api_main._ensure_data_files
        original_run = api_main.run_engine_v0

        def fake_run(_):
            return {
                "portfolio": [{"ticker": "SPY", "name_kr": "미국 S&P500 ETF", "weight": 1.0}],
                "metrics": {"exp_return": 0.06, "vol": 0.12, "est_mdd": 0.2},
                "accumulation_series": [{"date": "2030-01-31", "balance": 1000000, "principal": 900000, "gain": 100000}],
                "retirement_series": [{"date": "2030-02-28", "balance": 990000, "withdrawal": 10000, "gain": 90000}],
                "retirement_summary": {"start_balance_at_retirement": 1000000, "monthly_withdrawal": 10000, "duration_months": 240, "end_balance": 0},
                "warnings": [],
            }

        try:
            api_main._ensure_data_files = lambda: None
            api_main.run_engine_v0 = fake_run
            response = client.post(
                "/report",
                json={
                    "current_balance_krw": 10000000,
                    "monthly_contribution_krw": 500000,
                    "start_date": "2026-01-01",
                    "retirement_date": "2030-01-01",
                    "target_cagr": 6.0,
                    "max_mdd": 20.0,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("content-type"), "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF"))
        finally:
            api_main._ensure_data_files = original_ensure
            api_main.run_engine_v0 = original_run


if __name__ == "__main__":
    unittest.main()
