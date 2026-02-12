import unittest

from packages.engine.universe import select_representative_etfs


class UniverseSelectionTests(unittest.TestCase):
    def test_select_by_aum_then_expense(self):
        rows = [
            {"ticker": "A", "asset_class": "us_equity", "aum_krw": "100", "expense_ratio": "0.2"},
            {"ticker": "B", "asset_class": "us_equity", "aum_krw": "100", "expense_ratio": "0.1"},
            {"ticker": "C", "asset_class": "us_equity", "aum_krw": "90", "expense_ratio": "0.01"},
        ]
        selected = select_representative_etfs(rows, "us_equity", top_k=2)
        self.assertEqual([row["ticker"] for row in selected], ["B", "A"])

    def test_min_aum_filter(self):
        rows = [
            {"ticker": "A", "asset_class": "reits", "aum_krw": "9"},
            {"ticker": "B", "asset_class": "reits", "aum_krw": "11"},
        ]
        selected = select_representative_etfs(rows, "reits", top_k=3, min_aum_krw=10)
        self.assertEqual([row["ticker"] for row in selected], ["B"])


if __name__ == "__main__":
    unittest.main()
