# Blave Agent → JEI 官方收盤價模擬驗證介面（第一階段已實作）

來源：<https://github.com/Blave-TW/blave-agent>（Apache-2.0，僅參考公開資料與資料契約，未複製其交易程式碼）。

本整合是**可執行、可重現的本機資料適配器**：
`tools/jei_blave_bridge.py` 讀取 Blave Agent 匯出的 JSONL 訊號，對照 JEI
`remote/daily_prices.json` 封存的每日收盤價，使用 JEI
`scripts.forward_pick_score.score_pick` 現有的成本、持有交易日及資料缺漏驗證邏輯。
輸出獨立的 `audit-output/blave-comparison.json`；不修改正式選股、持股、LINE 或績效榜。

## 如何產生輸入

在你已安裝的 Blave 環境中，請 Agent **只在本機**把它在台股官方收盤後產生的
長倉候選訊號匯出成 UTF-8 JSONL，每行一個物件，且至少含下列欄位：

| 欄位 | 格式 | 說明 |
| --- | --- | --- |
| `signal_id` | 唯一文字 ID | 用來拒絕重複 |
| `generated_at` | ISO-8601、附時區 | 須為台灣同日 13:30 之後 |
| `data_asof` | YYYY-MM-DD | 訊號依據的同日官方收盤 |
| `ticker` | 台股數字代號或 ETF 代號 | 例如 2330、00937B |
| `market` | TW | 限台股 |
| `strategy_id` | 英數字、底線、破折號 | 策略版本固定，避免日後重命名覆寫 |
| `signal` | BUY / SELL / HOLD | 第一階段僅 BUY 計算多頭持有觀測 |
| `reference_price` | 正的有限數字 | 與 JEI 同日未調整收盤價差距須 ≤ 0.5% |
| `source` | blave-agent | 標明來源；但標籤不證明來源身分 |

假設交易訊號日 2026-10-13，範例格式如下（*純格式示範，價格並非聲明的真實行情*）：

```json
{"signal_id":"demo-20261013-2330","generated_at":"2026-10-13T14:10:00+08:00","data_asof":"2026-10-13","ticker":"2330","market":"TW","strategy_id":"sma20_60_v1","signal":"BUY","reference_price":100,"source":"blave-agent"}
```

執行：

```bash
python -m tools.jei_blave_bridge --signals /path/to/blave-signals.jsonl --prices remote/daily_prices.json --out audit-output/blave-comparison.json
python -m unittest discover -s tests -p 'test_jei_blave_bridge.py' -v
```

**守則：**
- 只分析使用者明確提供的本機公開研究訊號，**不會呼叫 Blave API，也不連接、控制或下單到任何券商帳戶**。
- 嚴格檢查資料日期、時區、13:30 收盤分界、來源日股價一致性、每日 ≥500 檔有效資料、
  串接的交易所日曆不可遺漏任一交易日。同股同日同策略與重複 ID 都拒絕。
- 訊號日後**下一個交易日收盤價**作為研究進場代理價，不冒充開盤成交；3/7/15/30/60 交易日成熟後才算回報。
  未來價格缺漏標記 `pending` 或 `unavailable`，不當成獲勝或刪掉失敗案例。
- 考量 JEI 原有手續費、交易稅和滑價預設；完整歷史除權息、停牌、買不到的漲停股等尚須另行驗證。
- 如果來源價格為 Blave **還原權息價格**而 JEI 使用未調整收盤價，適配器刻意拒絕，不自動換算。
- SELL/HOLD 不計為已成交多空交易；不能用這個報告宣稱 DQN 模型已訓練、策略已通過樣本外 walk-forward、
  勝率已達 80% 或與 Blave 伺服器真實完成串接。
- 不加入私人持股、成本、密鑰或其他敏感資料，也不把輸出直接寫入公開遠端 JSON。

## 後續驗收

1. 用從 Blave 工作區**真正匯出**的訊號核對資料格式、授權與來源真偽。
2. 與 JEI 同日同股票、同進場規則、同成本，計算獨立比較表，控制資料洩漏與存活者偏差。
3. 對 DQN 研究模型另做訓練集與測試集的時間切割、防洩漏驗證；不要用歷史訓練獲利當作實盤勝率。
4. 取得足夠獨立樣本後再考慮是否上線研究頁；不接真實下單。
