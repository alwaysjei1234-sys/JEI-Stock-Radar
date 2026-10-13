"""Offline generator integration: public quotes, ETFs, privacy and daily archive."""
import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("feed", Path(__file__).parents[1] / "scripts/update_system.py")
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)

class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 12, 16, 30, tzinfo=tz)

twse = [{"Date": "1151012", "Code": str(1000 + i), "Name": "測試股",
         "ClosingPrice": "103", "Change": "3", "OpeningPrice": "100",
         "HighestPrice": "104", "LowestPrice": "99", "TradeVolume": "10000000",
         "TradeValue": "1030000000"} for i in range(600)]
twse.append({**twse[0], "Code": "00937B", "Name": "測試 ETF"})
tpex = [{"Date": "1151012", "SecuritiesCompanyCode": "2609", "CompanyName": "測試股",
         "Close": "66", "Change": "6", "Open": "60", "High": "66", "Low": "60",
         "TradingShares": "10000000", "TransactionAmount": "660000000"}]
feed.datetime = FixedDate
feed.fetch_json = lambda url, *a, **k: twse if url == feed.TWSE_STOCK else tpex if url.startswith(feed.TPEX_STOCK) else {}
feed.fetch_institutional = lambda: ({}, [], {})
with tempfile.TemporaryDirectory() as root:
    feed.OUT = Path(root) / "system.json"
    feed.HISTORY = Path(root) / "history.json"
    feed.DAILY_PRICES = Path(root) / "daily_prices.json"
    feed.main()
    data = json.loads(feed.OUT.read_text())
    assert data["holdings"] == {}
    assert data["quotes"]["2609"]["price"] == 66
    assert data["quotes"]["00937B"]["price"] == 103
    assert data["quotes"]["2609"]["data_date"] == "2026-10-12"
    assert data["quotes"]["2609"]["kind"] == "daily_close"
    assert all(not {"cost", "shares", "pnl", "market_value"}.intersection(q) for q in data["quotes"].values())
    assert len(json.loads(feed.DAILY_PRICES.read_text())["days"]["2026-10-12"]) >= 500
    assert data["attack"], "generator must reach candidate scoring, not just quote serialization"
print("PASS full generator: scoring, close quotes, ETF, date, privacy, daily archive")
