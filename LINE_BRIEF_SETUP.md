# JEI LINE 開盤早報與盤後復盤

## 現有功能

- 手機可直接開啟 `https://jei-stock-radar.vercel.app/remote/brief.html`，或從 JEI 總覽進入。
- 交易日台灣時間 **08:00** 產生開盤前早報，**15:30** 嘗試盤後復盤，**18:10** 再確認官方收盤完整度。
- 採 GitHub Actions 排程，執行時間可能因 GitHub 排隊而延後，並非保證準時。
- 早報：最近一個可驗證美股收盤、帶來源與時間的近期新聞、台股收盤基準、大盤風控、族群和主攻觀察。
- 復盤：今日已驗證台股收盤、大盤風控、族群強弱、主攻候選、四策略的最新模擬績效。
- 研究報告是公開市場版，不會讀取你的本機私人持股／成本，也不會把持股寫回 GitHub。
- 沒有 Email；不連接真實券商或自動下單。

## LINE 自動推播（預設不啟用）

使用官方 LINE Messaging API 的 Push API，不使用 LINE Notify。必須有你自己管理的 **LINE 官方帳號**。免費輕用量方案在台灣每月有 200 則免費訊息（方案可能調整，使用前以 LINE 官網為準）。

1. 在 [LINE Official Account Manager](https://manager.line.biz/) 建立帳號，啟用 Messaging API，並加這個官方帳號為好友。
2. 在 [LINE Developers Console](https://developers.line.biz/console/) 取得官方帳號的 Channel access token，與你自己正確的 LINE User ID。若你的 Business ID 已連結 LINE 帳號，可以在該 Messaging API channel 的 **Basic settings → Your user ID** 查看；否則需依 LINE 官方 Webhook 取得。**LINE ID（自訂用戶名稱）不是 User ID**。
3. 進入 GitHub `JEI-Stock-Radar → Settings → Secrets and variables → Actions`，新增 Repository secrets：
   - `JEI_LINE_CHANNEL_ACCESS_TOKEN`：Channel access token
   - `JEI_LINE_USER_ID`：你的私人 User ID（`U` 開頭加 32 位十六進位碼）
4. 在同一頁 Repository **Variables** 增加 `JEI_LINE_ENABLED`，值設為 `true`。沒有完成前 LINE 發送保持關閉。
5. 交易日 08:00（早報）及 18:10（收盤驗證後）會自動嘗試送出 **單一私人收件人** 1 則文字推播；15:30 僅生成頁面，不推播。
6. 同日同類型使用 LINE 官方 X-Line-Retry-Key 24 小時去重，且每次送出前以 LINE Quota API 檢查使用量。**只允許免費額度上限不大於 200 的方案、單月使用量少於 55 則**；若額度／憑證查詢失敗就不發送，避免使用有額外收費的方案。
7. 不提供 Email 寄送。

**保護金鑰：** 絕對不要把 Channel access token 或 User ID 貼到 GitHub 公開程式碼、LINE 群組或 ChatGPT 對話；請直接在 GitHub Secret 設定頁輸入。

## 可驗收項目

- `python -m unittest discover -s tests -p 'test_daily_brief.py' -v`
- `python scripts/build_daily_brief.py --edition close`（會更新 `remote/brief.json`）
- 手機瀏覽報告，確認顯示的資料日／驗證狀態、新聞來源、模擬日期。
- Secret 尚未配置時應顯示 LINE 未啟用，且不發送。
- LINE 憑證設定完成後，測試下一個交易日早報（注意 GitHub 排程可能延遲）。

## 尚未完成的部分

- 針對 **你的私人持股** 的每日新聞與損益報告：尚未建立安全的個人化雲端持股資料來源；公開報告不能偷帶手機裡的持股。
- LINE 使用者自行選擇推播條件、任意價位通知、持股與 ETF 的全資產統計。
- 美股 Yahoo 日線、Google News RSS 可能失敗或延遲；程式應標示無法驗證，而不是製造行情或新聞。
- 沒有筆電也能使用本次 **雲端 GitHub＋手機網頁**，但 LINE 官方帳號與 Secret 仍須本人設定。


## 盤中大逃殺／飆股 LINE 警報（已依使用者指示啟用）

2026/10/17 新增 `scripts/send_line_alert.py`，由原本的 `Update JEI Market Feed` 排程（交易日大約每 15 分鐘）**在行情資料成功更新後**檢查。

- **啟用方式（2026/10/18）：** 在使用者確認真實 LINE 測試成功並要求「開始」後，GitHub 正式工作流程將盤中通知與已存在的 `JEI_LINE_ENABLED=true` **總開關**連動，不必再次新增 Variables。預設仍須有已設定的官方 LINE Token、收件者與總開關，且只有可信行情與條件達標才會發出。若要**只關閉盤中額外推播**（保留早報、復盤），到 GitHub → Settings → Secrets and variables → Actions → Variables 設定 `JEI_LINE_ALERTS_ENABLED=false`；也可以將 `JEI_LINE_ENABLED=false` 關閉全部 LINE 推播。
- **資料條件：** 台灣交易日 09:00–13:29、今日市場資料、至少 500 檔有效盤中成交、系統時間戳不超過 35 分鐘、`live_valid=true`、`stale=false`；少一個條件即停止。
- **大逃殺警戒：** JEI 市場 `risk.level=red` 且風險分數至少 75，傳送含來源日／市場風險原因的提醒；不直接建議或執行委託。
- **強勢股觀察：** 大盤風險分數低於 60，且已驗證的盤中「突然妖股」榜內出現評分至少 95、漲幅 4%–10%、有正價格的股票，才發送最多 3 檔研究觀察；不能理解為隔日漲停保證。
- **節流：** 每交易日最多一筆「大盤紅色高風險」及一筆「強勢股觀察」；兩種警報使用不同的 LINE `X-Line-Retry-Key`，避免早上先發強勢股、午後出現大逃殺時漏報。LINE 官方免費額度和每月 55 則的程式保護仍然生效。巡檢每 15 分鐘不代表每次發訊。
- **隱私：** 僅公開市場總體警報，不含持股、成本、聊天內容、LINE 個資。私人持股 LINE 預警仍須另做安全的私有架構。
- **時效限制：** GitHub Actions 會延遲、交易所行情接口可能拒絕或降級，這是盡力而為的準盤中通知，**不是交易所即時逐筆報價／秒級推播**。

驗證方式：`python -m unittest discover -s tests -p 'test_line_alert.py' -v`；先在未啟用額外開關時觀察 GitHub Actions 中「沒有發送」的安全行為，再決定是否啟用。

## Android 3.9.11 原生通知測試（2026/10/18）

Android App 3.9.11（versionCode 35）「持股 → Android 背景風險通知紀錄」新增「**測試手機通知**」按鈕。它直接使用手機 Android NotificationManager 發出一筆**明確標為測試**的本地通知並記錄測試，不會發送 LINE、製造假股價或下單。若手機未允許通知、通知頻道遭關閉，會顯示原因。瀏覽器／舊 APK 不能冒充原生通知成功。

背景警示比照選股和 LINE 的有效行情門檻，新增 `live_count >= 500`，且維持只有有效盤中成交、未過期資料才能觸發。WorkManager 執行時間仍受手機系統排程與省電機制限制。
