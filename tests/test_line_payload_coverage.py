"""Exercise the real brief producer and LINE's UTF-16 message budget offline."""
import copy
import unittest
from scripts import build_daily_brief as brief
from scripts import send_line_brief as line
import test_daily_brief as fixtures


class LinePayloadCoverageTests(unittest.TestCase):
    def text(self, report):
        return line.payload(report, 'fixture')['messages'][0]['text']

    def morning(self):
        now, feed, archive = fixtures.BriefTests().retained_case()
        quote = lambda name: {'name':name, 'date':'2026-10-30', 'close':100,
                              'change_pct':1, 'source':'Yahoo Finance'}
        return brief.generate('morning', now, feed, fixtures.PAPER,
            us_fn=lambda n:[quote(x) for x in ['S&P 500','NASDAQ','道瓊']],
            global_fn=lambda n:[quote(x) for x in ['費城半導體','VIX','台積電 ADR','WTI','美元指數','美元／新台幣','日經','韓國']],
            news_fn=lambda n:[], archive=archive)

    def test_actual_six_block_morning_keeps_the_previously_dropped_candidates(self):
        report = self.morning()
        text = self.text(report)
        self.assertEqual(len(report['blocks']), 6)
        self.assertIn('歷史主攻候選（非今日選股）', text)
        self.assertIn('2344 華邦電', text)
        self.assertIn('非今日即時行情或新選股', text)
        self.assertNotIn('NEVER_PUBLIC', text)

    def test_normal_morning_keeps_all_core_cross_market_quotes(self):
        text = self.text(self.morning())
        for name in ['道瓊','台積電 ADR','美元指數','美元／新台幣','日經','韓國']:
            self.assertIn(name, text)
        self.assertIn('未獨立驗證收盤', text)

    def test_long_messages_always_keep_the_complete_report_link_and_disclaimer(self):
        url = 'https://jei-stock-radar.vercel.app/remote/brief.html'
        report = {'title':'標題'*3000, 'note':'說明'*3000, 'date':'2026-11-05',
                  'report_url':url, 'blocks':[{'title':'區塊'+str(i), 'items':['文'*500]*8} for i in range(20)]}
        text = self.text(report)
        self.assertLessEqual(len(text.encode('utf-16-le'))//2, 3500)
        self.assertIn('詳細內容：'+url, text)
        self.assertTrue(text.endswith('僅研究參考，非即時行情或買賣建議。'))

    def test_utf16_budget_counts_emoji_without_cutting_the_footer(self):
        report = {'title':'📈'*120, 'note':'🚀'*400, 'blocks':[
            {'title':'行情'+str(i), 'items':['📈'*180]*2} for i in range(8)]}
        text = self.text(report)
        self.assertLessEqual(len(text.encode('utf-16-le'))//2, 3500)
        self.assertIn('詳細內容：https://jei-stock-radar.vercel.app/remote/brief.html', text)

    def test_critical_blocks_survive_many_long_lower_priority_sections(self):
        paper = brief.paper_block({'last_processed_day':'2026-11-05','strategies':{
            str(i):{'name':'策略'+str(i),'summary':{'estimated_liquidation_equity_ntd':1000000,'closed':10,'wins':1}}
            for i in range(4)}}, '2026-11-05')
        report = {'blocks':[{'title':'補充'+str(i), 'items':['低優先'*100]*2} for i in range(20)]+[
            {'title':'大盤風控','items':['風險標記']},
            {'title':'主攻候選（非下單訊號）','items':['候選標記']}, paper]}
        text = self.text(report)
        for item in ['風險標記','候選標記','策略0','策略1','策略2','策略3','樣本外']:
            self.assertIn(item, text)

    def test_payload_keeps_one_text_message_and_does_not_mutate_the_report(self):
        report = self.morning(); before = copy.deepcopy(report)
        result = line.payload(report, 'fixture')
        self.assertEqual(len(result['messages']), 1)
        self.assertEqual(result['messages'][0]['type'], 'text')
        self.assertEqual(result['to'], 'fixture')
        self.assertFalse(result['notificationDisabled'])
        self.assertEqual(report, before)

    def test_malformed_sections_are_skipped_without_dropping_the_valid_notice(self):
        text = self.text({'blocks':[None,'bad',{'title':'bad','items':None},
                                  {'title':'未發布原因','items':['驗證失敗','不提供選股']} ]})
        self.assertIn('驗證失敗', text)
        self.assertIn('不提供選股', text)


if __name__ == '__main__':
    unittest.main()
