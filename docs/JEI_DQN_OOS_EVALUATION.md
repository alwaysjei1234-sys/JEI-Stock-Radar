# JEI DQN 研究模型：樣本外輸出驗收接點（不會下單）

參考：<https://github.com/sachink2010/AutomatedStockTrading-DeepQ-Learning>
（MIT license；此整合不複製其舊版模型權重、Notebook 或交易程式碼）。

這一階段已實作 `tools/jei_dqn_oos_bridge.py`：讓外部 DQN
**實驗輸出**與 JEI 使用相同台股日期、成本及收盤代理進出場規則，
而不把模型訓練期間的績效混入樣本外成果。

## 使用方式

1. 在隔離的研究電腦或 Colab 訓練 DQN，不輸入任何真實下單金鑰。
2. 固定模型版本及每版的 `trained_through` 訓練截止日；先保留模型檔與訓練紀錄。
3. 把每日收盤後產生的策略輸出匯成 **一行一物件的 JSONL**。沿用
   [Blave 介面契約](./BLAVE_JEI_SIGNAL_ADAPTER.md)，但固定：
   - `source`: `dqn-experiment`
   - `split`: `train` 或 `oos`
   - `model_version`: 訓練版本或檢查點識別碼，不得重複用於不同截止日
   - `trained_through`: 該模型**已使用過**資料的最後交易日期
4. 執行：

```bash
python -m tools.jei_dqn_oos_bridge --actions ./dqn-actions.jsonl \
  --prices remote/daily_prices.json --out audit-output/dqn-oos-comparison.json
python -m unittest discover -s tests -p 'test_jei_dqn_oos_bridge.py' -v
```

## 驗證與限制

- `split=train` 不參加測試勝率；`split=oos` 的 `data_asof` 必須嚴格晚於 `trained_through`。
- 同版本不得偷偷延長訓練集；不同版本可各自記錄截止日，但**不能**因此自動宣稱完成滾動樣本外驗證。
- 13:30 後有時區的訊號、不可重複的標的／策略／日期、官方收盤價一致性和交易日缺漏驗證均使用同一套 JEI 引擎。
- 僅 `BUY` 訊號計算多頭紙上觀測；`SELL/HOLD` 不計為已執行的短線交易。
- 只產生本機 `audit-output` 報告，沒有發送 LINE、接券商、修改 JEI 推薦或自動下單。
- 這份報告的 train/OOS 標籤是**模型輸出自述**：目前尚未核對模型權重、訓練程式、不可見測試集、
  參數掃描、特徵資料時間戳與真正的 walk-forward 切割，因此
  `model_training_verified`、`independent_oos_verified` 和
  `walk_forward_verified` 一律為 `false`。

下一步才是將該參考專案的模型訓練程式於隔離環境重製，加入
固定種子、資料來源時戳、特徵洩漏測試、時序切割、多市場狀態、
交易成本及最大回撤，並以相同股票期間與 JEI 基準法比較。
**不能用示範 Notebook 的訓練收益充當 JEI 已有 80% 命中率。**
