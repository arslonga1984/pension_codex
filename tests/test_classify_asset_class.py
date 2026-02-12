import unittest

from packages.data.classify_asset_class import classify_asset_class


class ClassifyAssetClassTests(unittest.TestCase):
    def test_us_equity_keywords(self):
        self.assertEqual(classify_asset_class("미국 S&P500 인덱스 ETF"), "us_equity")

    def test_global_equity_keywords(self):
        self.assertEqual(classify_asset_class("MSCI ACWI 전세계 주식"), "global_equity")

    def test_korea_treasury_keywords(self):
        self.assertEqual(classify_asset_class("국고채 10년 추종 ETF"), "korea_treasury")

    def test_reits_keywords(self):
        self.assertEqual(classify_asset_class("미국 리츠 부동산 ETF"), "reits")

    def test_gold_keywords(self):
        self.assertEqual(classify_asset_class("KRX 금 현물 ETF"), "gold")

    def test_unknown_when_empty_or_ambiguous(self):
        self.assertEqual(classify_asset_class(""), "unknown")
        self.assertEqual(classify_asset_class("알수없는테마"), "unknown")


if __name__ == "__main__":
    unittest.main()
