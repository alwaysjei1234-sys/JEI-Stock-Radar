"""JEI Colab audit port: offline/local GitHub Actions, no Drive or credentials."""
import argparse
import datetime as dt
import json
import pathlib
import sys

from scripts.public_holding_signals import is_safe_public_holdings
from tools.jei_colab_watchdog import assess

REQUIRED = ('updated_at', 'summary', 'risk', 'market', 'holdings', 'priority', 'attack',
            'next', 'monster', 'rotate', 'flow', 'backtest')
AREAS = ['LINE 實際送達','盤中行情刷新','TWSE/TPEx/MIS 交叉驗證','休市與資料新鮮度','市場紅燈預警',
'Android 實機顯示','遠端 UI 更新','主流資金','強勢族群','量價突破','妖股偵測',
'每日選股歸檔','現股模擬','當沖模擬','3日績效','7日績效','15日績效','30日績效',
'樣本外 walk-forward','持股健檢模組1','持股健檢模組2','持股健檢模組3',
'持股健檢模組4','持股健檢模組5','持股健檢模組6','持股健檢模組7','持股健檢模組8',
'AI多模型會診','外部研究來源核對','Vercel部署驗收','完整31項回歸測試']

def inspect_feed(feed):
    issues = ['missing:' + key for key in REQUIRED if key not in feed]
    if "holdings" in feed:
        holdings = feed["holdings"]
        if not isinstance(holdings, dict) or not is_safe_public_holdings(holdings):
            issues.append("invalid_public_holdings")
    risk, market = feed.get('risk') or {}, feed.get('market') or {}
    date = feed.get('data_date') or feed.get('source_data_date')
    try:
        dt.date.fromisoformat(date)
    except (ValueError, TypeError):
        issues.append('invalid_data_date')
    if risk.get('level') in ('red', 'orange') and not isinstance(risk.get('score'), (int, float)):
        issues.append('invalid_risk_score')
    # An explicit failed official-close refresh is a genuine data integrity failure,
    # unlike zero live quotes outside the trading session.
    if market.get('post_close_refresh') is True and market.get('stale') is True:
        issues.append('stale_official_close')
    if market.get('post_close_refresh') is True and market.get('session_status') != '已驗證':
        issues.append('unverified_official_close')
    if market.get("post_close_refresh") is True and market.get("session_status") == "已驗證":
        declared_dates = (feed.get("source_data_date"), market.get("market_data_as_of"))
        if any(value is not None and value != date for value in declared_dates):
            issues.append("official_close_date_mismatch")
    if market.get('live_valid') is False and market.get('live_count', 0) == 0:
        issues.append('live_not_verified (may be expected outside session)')
    institutional_status = feed.get('institutional_status')
    if isinstance(institutional_status, dict) and institutional_status.get('ok') is False:
        issues.append('institutional_unverified (institutional scoring must remain disabled)')
    critical = [issue for issue in issues if issue.startswith('missing:') or issue in ('invalid_data_date', 'invalid_risk_score', 'invalid_public_holdings', 'official_close_date_mismatch', 'stale_official_close', 'unverified_official_close')]
    return {'status': 'failed' if critical else 'ok', 'critical_issues': critical,
            'feed_date': date, 'updated_at': feed.get('updated_at'),
            'risk_level': risk.get('level'), 'risk_score': risk.get('score'),
            'live_valid': market.get('live_valid'), 'live_count': market.get('live_count'),
            'institutional_verified': (institutional_status.get('ok') is True if isinstance(institutional_status, dict) else None),
            'issues': issues, 'line_delivery': 'NOT_TESTED', 'android_device': 'NOT_TESTED'}

def heartbeat_status(path=None, now=None):
    payload = None
    if path:
        try:
            payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return assess(payload, now=now)


def build_report(feed, commit, heartbeat_path=None):
    return {'checked_at_taipei': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
            'repo': 'alwaysjei1234-sys/JEI-Stock-Radar', 'source_commit': commit,
            'baseline_completed': 15.5, 'baseline_total': 31,
            'completion_percent': None, 'completion_note': '31-item revalidation not performed',
            'colab_heartbeat': heartbeat_status(heartbeat_path),
            'results': inspect_feed(feed)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--feed', default='remote/system.json')
    parser.add_argument('--out', default='audit-output')
    parser.add_argument('--commit', default='unknown')
    parser.add_argument('--heartbeat', help='Optional readable heartbeat JSON; absent means UNKNOWN')
    args = parser.parse_args()
    output = pathlib.Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    try:
        feed = json.loads(pathlib.Path(args.feed).read_text(encoding='utf-8'))
        report = build_report(feed, args.commit, args.heartbeat)
        status = 1 if report['results']['critical_issues'] else 0
    except (OSError, ValueError, TypeError) as exc:
        report = {'error': str(exc), 'completion_percent': None,
                  'line_delivery': 'NOT_TESTED', 'android_device': 'NOT_TESTED'}
        status = 1
    (output / 'jei_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    checklist = [{'id': i + 1, 'working_label': label, 'status': 'NOT_VERIFIED',
                  'evidence': None, 'note': '工作分類，尚需與正式31項核對'}
                 for i, label in enumerate(AREAS)]
    (output / 'working_31_item_checklist.json').write_text(
        json.dumps(checklist, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return status

if __name__ == '__main__':
    sys.exit(main())
