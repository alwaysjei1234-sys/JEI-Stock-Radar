import unittest

from scripts.update_system import sector_evidence


class SectorEvidenceTests(unittest.TestCase):
    def test_uncovered_sector_is_not_presented_as_measured_neutral_heat(self):
        self.assertEqual(sector_evidence("未分類", 50), "族群資料未涵蓋（中性計分）")

    def test_measured_sector_keeps_its_measured_heat(self):
        self.assertEqual(sector_evidence("半導體", 77), "半導體熱度 77")


if __name__ == "__main__":
    unittest.main()
