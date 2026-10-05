# JEI 專屬選股雷達 V2

Android 個人選股與持股管理 App。

## V2 已完成核心

- Android 原生 WebView shell，離線仍可開啟。
- 每次啟動自動抓 `remote/index.html`，介面與前端邏輯可以遠端更新，不必每次重裝 APK。
- 台灣證交所 MIS 行情由 Android 原生層連線，避免 WebView CORS。
- `remote/system.json` 是 JEI 選股、持股決策與大逃殺風控 feed。
- 60 秒盤中行情刷新，APP 回到前景時立即刷新。
- App 版本檢查透過 `remote/update.json`。
- GitHub Actions 會自動編譯可安裝 Android APK。

## 資料架構

1. TWSE MIS：持股即時/近即時行情。
2. JEI remote feed：今日主攻、下一棒、突然妖股、換股、資金流與風險。
3. Android SharedPreferences：持股成本與股數。
4. Remote UI：啟動時自動抓最新介面，失敗則使用 APK 內建版本。

> 若 repository 維持 Public，不要把個人金融資料寫入 remote JSON。
