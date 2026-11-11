import copy
import unittest
from unittest.mock import patch
from scripts import update_system as u

DAY = '2026-11-03'

class InstitutionalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.twse = {'stat':'OK','date':'20261103',
                     'fields':['證券代號','外陸資買賣超股數(不含外資自營商)','投信買賣超股數','自營商買賣超股數','三大法人買賣超股數'],
                     'data':[['2330','-1000','0','0','-1000']]}
        self.tpex = [{'Date':'1151103','SecuritiesCompanyCode':'6488',
                      'Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference':'0',
                      'SecuritiesInvestmentTrustCompanies-Difference':'0',
                      'Dealers-Difference':'2000','TotalDifference':'2000'}]

    def fetch(self, twse=None, tpex=None):
        def get(url):
            value = (self.tpex if tpex is None else tpex) if url == u.TPEX_INST else (self.twse if twse is None else twse)
            if isinstance(value,Exception): raise value
            return copy.deepcopy(value)
        with patch.object(u,'fetch_json',side_effect=get):
            return u.fetch_institutional(DAY)

    def test_both_same_day_sources_have_dated_totals(self):
        rows, errors, _ = self.fetch()
        self.assertEqual(errors,[])
        self.assertTrue(u.institutional_market_complete(rows,errors,DAY))
        self.assertEqual(rows['2330']['data_date'],DAY)
        self.assertEqual(rows['6488']['total'],2000)

    def test_twse_old_missing_future_invalid_date_or_status_rejected(self):
        for field,value in [('date','20261102'),('date',None),('date','20261104'),('date','20261303'),('stat','FAIL')]:
            with self.subTest(field=field,value=value):
                source=copy.deepcopy(self.twse);source[field]=value
                rows,errors,_=self.fetch(twse=source)
                self.assertNotIn('2330',rows)
                self.assertIn('6488',rows)
                self.assertFalse(u.institutional_market_complete(rows,errors,DAY))

    def test_tpex_mixed_old_missing_or_invalid_date_rejects_entire_market(self):
        for date in ['1151102',None,'1151303']:
            with self.subTest(date=date):
                mixed=copy.deepcopy(self.tpex)+[{'Date':date,'SecuritiesCompanyCode':'8086','TotalDifference':'-9'}]
                rows,errors,_=self.fetch(tpex=mixed)
                self.assertEqual(set(rows),{'2330'})
                self.assertFalse(u.institutional_market_complete(rows,errors,DAY))

    def test_one_market_outage_does_not_become_full_market_even_with_500_rows(self):
        rows,errors,_=self.fetch(twse=OSError('temporary unavailable'))
        many={str(i):dict(rows['6488']) for i in range(800)}
        self.assertFalse(u.institutional_market_complete(many,errors,DAY))

    def test_zero_is_valid_but_missing_or_nonfinite_totals_are_not(self):
        for total,complete in [('0',True),(None,False),('NaN',False),('inf',False)]:
            with self.subTest(total=total):
                source=copy.deepcopy(self.tpex);source[0]['TotalDifference']=total; source[0]['Dealers-Difference']=total
                rows,errors,_=self.fetch(tpex=source)
                self.assertEqual(u.institutional_market_complete(rows,errors,DAY),complete)

    def test_tpex_foreign_dealers_are_not_included_in_foreign_total(self):
        source = copy.deepcopy(self.tpex)
        source[0]["ForeignInvestorsInclude MainlandAreaInvestors-Difference"] = "15"
        source[0]["ForeignDealers-Difference"] = "15"
        rows, errors, _ = self.fetch(tpex=source)
        self.assertEqual(rows["6488"]["foreign"], 0)
        self.assertTrue(u.institutional_market_complete(rows, errors, DAY))

    def test_same_date_with_unreconciled_components_stops_market_scoring(self):
        for field, value in [
            ("Dealers-Difference", "0"),
            ("SecuritiesInvestmentTrustCompanies-Difference", "0.5"),
            ("Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference", None),
        ]:
            with self.subTest(field=field):
                source = copy.deepcopy(self.tpex)
                source[0][field] = value
                rows, errors, _ = self.fetch(tpex=source)
                self.assertNotIn("6488", rows)
                self.assertTrue(errors)
                self.assertFalse(u.institutional_market_complete(rows, errors, DAY))

    def test_twse_wrong_sum_blocks_market_scoring_even_with_valid_tpex(self):
        source = copy.deepcopy(self.twse)
        source["data"][0][-1] = "1000"
        rows, errors, _ = self.fetch(twse=source)
        self.assertEqual(set(rows), {"6488"})
        self.assertTrue(errors)
        self.assertFalse(u.institutional_market_complete(rows, errors, DAY))

    def test_same_day_retry_preserves_verified_history(self):
        prior={'date':DAY,'institutional_market':{'verified':True,'data_date':DAY,'sell_ratio':65,'net_lots':-5}}
        out=u.update_history([prior],DAY,[{'code':'2330','close':100}],[],None)
        self.assertEqual(out[0]['institutional_market'],prior['institutional_market'])

    def test_legacy_or_wrong_day_breadth_is_not_promoted(self):
        for value in [{'sell_ratio':65},{'verified':True,'data_date':'2026-11-02','sell_ratio':65}]:
            prior={'date':DAY,'institutional_market':value}
            self.assertNotIn('institutional_market',u.update_history([prior],DAY,[],[],None)[0])

if __name__=='__main__': unittest.main()
