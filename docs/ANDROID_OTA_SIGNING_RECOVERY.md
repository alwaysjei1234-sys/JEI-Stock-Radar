# JEI Android 原機覆蓋更新：安全簽章恢復

## 現況與限制

- 手機 App 套件為 `com.jei.stockradar`。原公開版 V42 使用的 APK 簽署憑證 SHA-256 為
  `807326371643b70ec340b8fd526568adb9ff86c8186e059ca6bc5d0633e4cbdd`。
- 2026-11-15 的正式建置雖成功編出 APK，但快取取回的憑證指紋為
  `a6221800794b3a5560cbcf09ffcf3bb1ed6bfd2ae2828042081a852b2d4256a0`，與 V42 不符，發布已被阻擋。
- 簽署憑證的**公開指紋不是私鑰**。無法從 APK 或指紋反推原私鑰，也不能只改 `expected` 來繞過 Android 簽章檢查。
- 已安裝不同簽章的舊版裝置可能仍不能覆蓋更新，需要先確認實際裝置簽章。不要強迫解除安裝：`android:allowBackup="false"` 且私人持股資料保存在本機。

## 恢復原簽章（只在有原始私鑰的情況下）

1. 從原始建置電腦或授權的安全備份中找回與上述 V42 指紋完全相符的原 Android 金鑰庫（.jks / .keystore）。若曾使用 GitHub Actions 快取，必須核對實際金鑰指紋，不可相信「Cache hit」。
2. **不可將原始私鑰、密碼或 base64 貼進聊天、Commit 或公開檔案。** 只能在 GitHub 專案的 Settings → Secrets and variables → Actions 設為 repository secrets：
   - `JEI_STABLE_KEYSTORE_B64`：**原始**金鑰庫檔案的 base64 內容
   - `JEI_STORE_PASSWORD`：原始 keystore 密碼
   - `JEI_KEY_ALIAS`：原始 key alias
   - `JEI_KEY_PASSWORD`：原始 key 密碼
3. 正式 workflow 驗證金鑰指紋等於 V42；失敗就拒絕發布，絕不產生另一把簽章金鑰。
4. 成功後組建 Release APK、檢查套件名稱、versionCode、versionName 與簽章，再上傳至 `jei-latest`。
5. 只有已上傳相容 APK 才同步更新 `remote/update.json`。如果發布或推送失敗，保留舊公告版本以避免誤導使用者。
6. 用**已安裝既有版本的 Android 實機**測試覆蓋更新，確認持股、數量、成本及設定仍在，再驗收版本檢查、下載、安裝及啟動。Android 安裝確認仍由作業系統處理，無法無提示靜默安裝。

## 無法找回原金鑰時

不能假裝「一鍵直接更新」已修好，也不能換一把金鑰冒充原版。應保留原 App 與持股資料，
另規劃由舊版導出、使用者確認後由新套件匯入的資料遷移方案；遷移經實機驗收前不得要求解除安裝。

## 驗收證據

- 原版與新 APK 相容的簽署憑證 SHA-256
- 相同 `applicationId`、新版更高 `versionCode`
- 正式 workflow 全部成功、更新清單指向該版本
- 安卓實機「直接覆蓋更新」及本機持股資料保留測試結果
