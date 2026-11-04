import unittest
from datetime import date,datetime,timezone
from scripts import update_working_capital as w


class WorkingCapitalTests(unittest.TestCase):
    def filing(self,changes='',facts=''):
        parts=['''<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
          xmlns:x="http://www.xbrl.org/2003/instance"
          xmlns:ifrs="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full"
          xmlns:tw="http://www.xbrl.org/tifrs/bsci/ci/2026-03-31"
          xmlns:currency="http://www.xbrl.org/2003/iso4217"
          xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2015-02-26"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">''']
        parts.append('<x:unit id="money"><x:measure>currency:TWD</x:measure></x:unit>')
        for year in (2026,2025):
            for kind in ('instant','duration','quarter','segment'):
                period=f'<x:instant>{year}-06-30</x:instant>' if kind in ('instant','segment') else f'<x:startDate>{year}-'+('04-01' if kind=='quarter' else '01-01')+f'</x:startDate><x:endDate>{year}-06-30</x:endDate>'
                parts.append(f'<x:context id="{year}-{kind}"><x:entity><x:identifier>6150</x:identifier></x:entity><x:period>{period}</x:period>'+('<x:scenario>segment</x:scenario>' if kind=='segment' else '')+'</x:context>')
            for concept,kind,value in [('ifrs:Inventories','instant',200 if year==2026 else 100),('tw:AccountsReceivableNet','instant',120 if year==2026 else 100),('ifrs:Revenue','duration',900 if year==2026 else 1000)]:
                parts.append(f'<ix:nonFraction name="{concept}" contextRef="{year}-{kind}" unitRef="money" format="ixt:numdotdecimal" scale="3">{value}</ix:nonFraction>')
        return (''.join(parts)+facts+changes+'</html>').encode()

    def parse(self,b):return w.parse_filing(b,'6150',2026,2,date(2026,11,4))

    def test_scale_entity_period_ytd_and_fixed_rules(self):
        r=self.parse(self.filing())
        self.assertEqual(r['current']['inventory'],200000)
        self.assertEqual(r['yoy_pct'],{'inventory':100.0,'receivables':20.0,'revenue_ytd':-10.0})
        self.assertEqual(r['alerts'],['inventory_growth_exceeds_revenue','receivables_growth_exceeds_revenue'])
        self.assertEqual(r['comparison_period_end'],'2025-06-30')
        self.assertTrue(r['not_for_historical_backtest'])

    def test_segment_and_single_quarter_cannot_replace_totals_and_ytd(self):
        facts='<ix:nonFraction name="ifrs:Revenue" contextRef="2026-quarter" unitRef="money" format="ixt:numdotdecimal">999</ix:nonFraction><ix:nonFraction name="ifrs:Inventories" contextRef="2026-segment" unitRef="money" format="ixt:numdotdecimal">888</ix:nonFraction>'
        r=self.parse(self.filing(facts=facts))
        self.assertEqual(r['current']['revenue_ytd'],900000)
        self.assertEqual(r['current']['inventory'],200000)

    def test_wrong_company_missing_facts_never_certifies_report(self):
        with self.assertRaises(ValueError):self.parse(self.filing().replace(b'>6150<',b'>2330<'))

    def test_conflicting_duplicate_refused_but_equal_duplicate_allowed(self):
        fact='<ix:nonFraction name="ifrs:Inventories" contextRef="2026-instant" unitRef="money" format="ixt:numdotdecimal" scale="3">VALUE</ix:nonFraction>'
        with self.assertRaises(ValueError):self.parse(self.filing(facts=fact.replace('VALUE','201')))
        self.assertEqual(self.parse(self.filing(facts=fact.replace('VALUE','200')))['status'],'comparable')

    def test_nil_wrong_unit_namespace_unknown_format_or_scale_is_missing(self):
        for before,after in [(b'name="ifrs:Inventories"',b'xsi:nil="true" name="ifrs:Inventories"'),
                (b'currency:TWD',b'currency:USD'),(b'xbrl.ifrs.org/taxonomy',b'example.com/taxonomy'),
                (b'ixt:numdotdecimal',b'ixt:unknown'),(b'scale="3"',b'scale="999"')]:
            with self.subTest(after=after):
                try:r=self.parse(self.filing().replace(before,after))
                except ValueError:continue
                self.assertEqual(r['status'],'partial')
                self.assertNotIn('inventory',r['current'])

    def test_prior_zero_missing_negative_or_nonfinite_does_not_create_growth(self):
        for value in ('0','NaN','Infinity','-100'):
            b=self.filing().replace(b'scale="3">100</ix:',('scale="3">'+value+'</ix:').encode())
            r=self.parse(b)
            self.assertIsNone(r['yoy_pct']['inventory'])
            self.assertNotIn('inventory_growth_exceeds_revenue',r['alerts'])

    def test_no_alert_for_falling_balances_even_if_revenue_falls_faster(self):
        b=self.filing().replace(b'>200</ix:',b'>80</ix:').replace(b'>900</ix:',b'>100</ix:')
        r=self.parse(b)
        self.assertNotIn('inventory_growth_exceeds_revenue',r['alerts'])

    def test_display_rounding_never_promotes_a_subthreshold_gap(self):
        b=self.filing().replace(b'>200</ix:',b'>119.9996</ix:').replace(b'>900</ix:',b'>1000</ix:')
        r=self.parse(b)
        self.assertEqual(r['yoy_pct']['inventory'],20.0)
        self.assertNotIn('inventory_growth_exceeds_revenue',r['alerts'])

    def test_future_reporting_period_and_xml_entities_refused(self):
        for b in (b'<!DOCTYPE html>'+self.filing(),b'<!ENTITY foo "bar">'+self.filing()):
            with self.assertRaises(ValueError):self.parse(b)
        with self.assertRaises(ValueError):w.parse_filing(self.filing(),'6150',2026,2,date(2026,6,29))

    def test_build_uses_only_public_tickers_and_declared_official_period(self):
        calls=[]
        def fetch(code,period,today):
            calls.append((code,period));return self.parse(self.filing())
        r=w.build({'holdings':{'6150':{'cost':'PRIVATE','qty':123},'00937B':{},'evil|url':{}}},
            {'markets':{'otc':{'6150':{'financials':{'period':'2026-Q2'}}}}},datetime(2026,11,4,tzinfo=timezone.utc),fetch)
        self.assertEqual(calls,[('6150','2026-Q2')])
        self.assertNotIn('PRIVATE',str(r));self.assertNotIn('qty',str(r))

    def test_failure_is_explicit_without_exception_content_or_old_numbers(self):
        def fetch(*args):raise ValueError('PRIVATE')
        r=w.build({'holdings':{'6150':{}}},{'markets':{'otc':{'6150':{'financials':{'period':'2026-Q2'}}}}},datetime(2026,11,4,tzinfo=timezone.utc),fetch)
        self.assertEqual(r['records']['6150']['status'],'unavailable')
        self.assertNotIn('PRIVATE',str(r))
        self.assertNotIn('current',r['records']['6150'])


if __name__=='__main__':unittest.main()
