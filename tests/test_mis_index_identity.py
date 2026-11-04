"""A fresh stock quote must never masquerade as the TAIEX market index."""
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u


class MisIndexIdentityTests(unittest.TestCase):
    now = datetime(2026, 11, 5, 10, 0, tzinfo=u.TZ)

    def quote(self, **changes):
        return {'c': 't00', 'ex': 'tse', 'ch': 't00.tw', 'd': '20261105',
                't': '09:59:00', 'y': '40000', 'z': '40400', **changes}

    def exercise(self, response):
        def fetch(channels):
            return response if channels == ['tse_t00.tw'] else []
        with patch.object(u, 'fetch_mis_channels', side_effect=fetch):
            return u.enrich_live([], self.now)

    def test_wrong_symbol_market_channel_and_missing_identity_never_set_index(self):
        for change in ({'c': '2330'}, {'ex': 'otc'}, {'ch': '2330.tw'},
                       {'c': None}, {'ex': None}, {'ch': None}):
            with self.subTest(change=change):
                self.assertIsNone(self.exercise([self.quote(**change)])[2])

    def test_expected_index_can_be_found_after_an_unrelated_stock(self):
        stock = self.quote(c='2330', ch='2330.tw', y='100', z='110')
        result = self.exercise([stock, self.quote()])
        self.assertAlmostEqual(result[2], 1.0)

    def test_identical_duplicates_are_safe_but_conflicting_index_rows_are_not(self):
        self.assertAlmostEqual(self.exercise([self.quote(), self.quote()])[2], 1.0)
        for change in ({'z': '40800'}, {'y': '39900'}, {'t': '09:58:59'}):
            with self.subTest(change=change):
                self.assertIsNone(self.exercise([self.quote(), self.quote(**change)])[2])

    def test_identity_does_not_bypass_exchange_date_time_or_price_gates(self):
        for change in ({'d': '20261104'}, {'t': '09:49:59'}, {'t': '10:01:01'},
                       {'t': '13:33:00'}, {'y': '-'}, {'z': 'NaN'}, {'y': 'Infinity'}):
            with self.subTest(change=change):
                self.assertIsNone(self.exercise([self.quote(**change)])[2])

    def test_malformed_response_or_entries_cannot_crash_the_index_check(self):
        for response in ({'c': 't00'}, 'invalid', [None, 'invalid', 1], None):
            with self.subTest(response=response):
                self.assertIsNone(self.exercise(response)[2])

    def test_valid_index_does_not_inflate_stock_coverage(self):
        rows, count, index, errors, stats = self.exercise([self.quote()])
        self.assertEqual((rows, count), ([], 0))
        self.assertAlmostEqual(index, 1.0)
        self.assertFalse(errors)
        self.assertEqual(stats['index_quote_status'], 'verified')

    def test_rejection_reason_is_visible_without_changing_stock_prices(self):
        rows = [{'code':'2330','market':'TWSE','close':100}]
        def fetch(channels):
            return [self.quote(c='2330', ch='2330.tw')] if channels==['tse_t00.tw'] else []
        with patch.object(u, 'fetch_mis_channels', side_effect=fetch):
            result, count, index, _, stats = u.enrich_live(rows, self.now)
        self.assertEqual(result, rows)
        self.assertEqual(count, 0)
        self.assertIsNone(index)
        self.assertEqual(stats['index_quote_status'], 'identity_mismatch')

    def test_nonfinite_calculated_percentage_is_rejected(self):
        self.assertIsNone(self.exercise([self.quote(z='1e308', y='1e-308')])[2])


if __name__ == '__main__':
    unittest.main()
