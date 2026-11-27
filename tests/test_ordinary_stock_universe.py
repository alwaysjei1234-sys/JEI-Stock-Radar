"""Synthetic prices with actual four-digit ETF symbol shapes; never live quotes."""
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u

ETF_CODES = ('0050', '0051', '0052', '0053', '0055', '0056', '0057', '0061')


def row(code, market='TWSE'):
    return {'code':code, 'name':'synthetic', 'close':10, 'pct':1,
            'market':market, 'date':'2026-11-27'}


class OrdinaryStockUniverseTests(unittest.TestCase):
    def test_four_digit_etfs_are_not_ordinary_stock_breadth(self):
        rows = [row(code) for code in (*ETF_CODES, '2330', '6488')]
        ordinary = [r['code'] for r in rows if u.stock_only(r)]
        self.assertEqual(ordinary, ['2330', '6488'])
        # Filtering analysis must not delete ETF quotes used by other views.
        self.assertEqual(len(rows), 10)
        self.assertIn('0050', {r['code']:r for r in rows})

    def test_etfs_cannot_fill_a_missing_ordinary_stock_coverage_gate(self):
        original = [row('2330')]
        twse = [row(str(3000+i)) for i in range(499)] + [row(c) for c in ETF_CODES]
        tpex = [row(str(7000+i), 'TPEX') for i in range(550)]
        now = datetime(2026,11,27,16,0,tzinfo=u.TZ)
        with patch.object(u, 'fetch_twse_daily', return_value=twse), \
             patch.object(u, 'fetch_tpex_daily', return_value=tpex):
            result, chosen = u.fetch_latest_offhours_close(original, now, '2026-11-26')
        self.assertIsNone(chosen)
        self.assertEqual(result, original)

    def test_invalid_numeric_values_never_count_as_ordinary_stock_analysis(self):
        self.assertTrue(u.stock_only({**row('2330'), 'pct':0}))
        for field, values in (('close', (-1, True, float('nan'), float('inf'))),
                              ('pct', (True, float('nan'), float('inf')))):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertFalse(bool(u.stock_only({**row('2330'), field:value})))

    def test_rejected_archive_price_cannot_fill_analysis_coverage(self):
        # A malformed synthetic OpenAPI row normalizes to a negative close
        # and finite percent. The archive already refuses that observation.
        invalid = u.norm_twse({'Date':'1151127', 'Code':'4999',
                               'Name':'synthetic', 'ClosingPrice':'-1', 'Change':'-2'})
        self.assertEqual(invalid['pct'], -200)
        self.assertEqual(u.official_close_observations([invalid], '2026-11-27')[0], {})
        twse = [row(str(3000+i)) for i in range(499)] + [invalid]
        tpex = [row(str(7000+i), 'TPEX') for i in range(550)]
        original = [row('2330')]
        now = datetime(2026,11,27,16,0,tzinfo=u.TZ)
        with patch.object(u, 'fetch_twse_daily', return_value=twse), \
             patch.object(u, 'fetch_tpex_daily', return_value=tpex):
            result, chosen = u.fetch_latest_offhours_close(original, now, '2026-11-26')
        self.assertIsNone(chosen)
        self.assertEqual(result, original)
