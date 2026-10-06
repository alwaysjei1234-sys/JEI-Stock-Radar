# JEI 多 AI 會診雲端

此資料夾提供 JEI Android App 的安全 AI 中繼層。**不要把任何 AI API Key 寫進 Android APK、remote/index.html 或 GitHub repository。**

## 支援
- ChatGPT / OpenAI Responses API
- Gemini GenerateContent API
- Claude Messages API
- Grok / xAI Chat Completions API
- 多 AI 平行會診 + JEI 綜合結論

## Vercel 環境變數
至少設定一家 AI 即可：

- `OPENAI_API_KEY`
- `OPENAI_MODEL`（可省略，預設 `gpt-5.6-luna`）
- `GEMINI_API_KEY`
- `GEMINI_MODEL`（可省略，預設 `gemini-3.6-flash`）
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`（可省略，預設 `claude-sonnet-4-5`）
- `XAI_API_KEY`
- `XAI_MODEL`（可省略，預設 `grok-4.5`）
- `JEI_CLIENT_TOKEN`：自訂一組長密碼，APP 端只存這支手機。

部署後 API 位址為：
`https://<your-vercel-project>.vercel.app/api/consult`

在 JEI App → 更新 →「多 AI 雲端」填入上述網址與 `JEI_CLIENT_TOKEN`。

## 隱私
APP 只把本次問題需要的市場摘要、候選榜、法人資料與持股資訊送到你自己的中繼層，再轉交你勾選的 AI 供應商。API Key 留在伺服器端。
