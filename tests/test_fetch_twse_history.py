"""Offline tests for TWSE history fetch validation."""
import unittest
from scripts.fetch_twse_history import fetch_month

class FetchValidationTests(unittest.TestCase):
    def test_invalid_month(self):
        with self.assertRaises(ValueError):
            fetch_month("2330","202613")
    def test_invalid_code(self):
        with self.assertRaises(ValueError):
            fetch_month("ABC","202610")

if __name__=="__main__":
    unittest.main()
