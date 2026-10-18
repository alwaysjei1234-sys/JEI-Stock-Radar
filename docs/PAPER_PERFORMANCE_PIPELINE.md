# JEI 現股選股績效：資料驗證與執行流程

## 已串接的真實來源
- `remote/system.json` 的 `data_date`：選股訊號所屬的**市場日期**，不可用更新時間代替。
- `attack` → `momentum`（強勢股）；`monster` → `monster`（妖股）；`future_monster` → `pre_breakout`（潛力妖股）。
- 每類最多保留前 10 檔；重複代號在同類當天只保留首次出現。
- 每個交易日於台灣時間 19:30 嘗試建立 `data/pick_snapshots/YYYY-MM-DD.json`。只有 feed 的 `data_date` 等於台灣當天日期才記錄，已存在的快照不覆寫。工作流程在 `.github/workflows/archive-daily-picks.yml`。

## 重要限制
- 這個自動化**從啟用之後開始累積**；不會憑空還原之前沒有保存的推薦。
- 只有提交到 GitHub 的原始快照才可當作歷史選股證據；人工補入的舊訊號應另標記來源，不能混為當日原始訊號。
- 選股快照只有訊號，不等於已成交。下一交易日收盤價只是研究代理價。
- **歷史個股收盤價、同期間加權指數價格尚須接入可信的歷史行情來源**。沒有價格時，績效顯示 pending，不可捏造。
- 當日 feed 尚未更新、假日或 GitHub Actions 沒有執行，可能沒有新快照；需檢查 Actions 日誌。
- 股利、除權息、停牌、下市、價格調整、成交量不足、漲跌停無法成交尚未完整納入；報告不是可交易的實際績效。
- 預設交易成本為買賣手續費每側 0.1425%、賣出交易稅 0.3%、每側滑價 0.1%，需依實際交易市場與折扣調整。
- 同一檔股票在不同日期或類別出現，屬不同訊號樣本；不等於獨立交易或獨立風險。

## 操作
```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m scripts.export_daily_picks --feed remote/system.json --output data/pick_snapshots/2026-10-16.json --limit 10
python -m scripts.collect_pick_snapshots --directory data/pick_snapshots --output /tmp/jei-picks.json
python -m scripts.paper_report --picks /tmp/jei-picks.json --prices /path/to/verified-daily-closes.json --benchmark /path/to/verified-index-closes.json --output /tmp/jei-report.json
```
第二行是手動範例，**只適用確定當日的原始 feed**；既有日期若已有檔案，程式會拒絕覆寫。不要以目前 feed 回填過往日期。

`prices` JSON 是股票代號到每日收盤價格陣列的映射；`benchmark` JSON 是同日期的指數收盤價陣列。所有日期採 ISO YYYY-MM-DD。請先驗證來源及交易日完整性。

## 2026-10：交易日與行情快照防呆
- 績效報告在提供基準指數每日收盤價時，以基準指數的**實際交易日期**定位第 3、7、15、30、60 個交易日。個股缺少進場或出場價格時標示 unavailable，避免以後一天的價格錯補。
- 同一盤後封存程序會額外記錄 `data/feed_closes/YYYY-MM-DD.json`，只讀 `remote/system.json` 各選股區塊的 `price` 欄位，並排除互相矛盾的價格。
- **feed.price 是當時 feed 的價格觀測，不是已經獨立查證的官方收盤價**。不應直接將它宣稱為已核實的績效行情；需要與 TWSE/TPEX 官方歷史資料對照。
- `data/feed_closes` 僅覆蓋有出現在推薦區塊的股票，不是完整市場每日價格，因此不能單靠此檔案直接完成長期績效。
- 已提交的定時任務不保證 GitHub Actions 已實際執行；請查閱 Actions 執行紀錄和當日快照是否產生。
