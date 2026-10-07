# JEI 免費多 AI 會診

JEI 3.9 改為 **零付費優先**。程式不再自動呼叫 Vercel AI Gateway，也不會因為免費額度用完而自動切到付費模型。

## 可用的免費來源

- Gemini Free：Google AI Studio 免費層，預設模型 `gemini-2.5-flash`
- Groq Free：`openai/gpt-oss-120b`
- Groq Free：`qwen/qwen3.8-27b`
- OpenRouter Free：`openrouter/free`，由 OpenRouter 在免費模型中路由

## 使用方式

在 JEI → 更新 →「免費多 AI 設定」貼上免費 API Key。Key 只儲存在目前手機/瀏覽器設定；每次會診時經由 HTTPS 傳到 JEI 自己的 Vercel 中繼層，程式庫不會保存或提交 Key。

可只設定其中一組。設定越多，多 AI 會診可得到越多獨立答案。某家免費額度或速率限制用完時，JEI 只略過該模型。

## Vercel 環境變數（可選）

若不想每台裝置各自輸入，也可在 Vercel 專案設定：
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`

`JEI_CLIENT_TOKEN` 仍用來保護 JEI 中繼 API，與 AI 計費無關。

## 重要

ChatGPT、Claude、Grok 的一般免費網頁帳號不等於免費 API，因此 JEI 不會冒用這些名稱。免費會診只顯示實際被呼叫的模型/服務。
