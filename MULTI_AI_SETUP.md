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

## Ollama Cloud（可選；無需筆電）

- 本機 Ollama 預設位於 `http://localhost:11434`，部署在 Vercel 的 JEI API 無法直接連到你家電腦的 localhost；因此目前新增的是 **Ollama Cloud**，而不是本機模型。
- Ollama 雲端 API：`https://ollama.com/api/chat`；預設 `gemma4:31b`，可用 Vercel 的 `OLLAMA_CLOUD_MODEL` 修改。
- 請在 Ollama 官網申請 API Key，然後在 **Vercel 專案環境變數**加入 `OLLAMA_API_KEY`（僅伺服器端讀取）。不要貼到公開 GitHub、瀏覽器網址、程式碼或聊天訊息中。
- 返回 JEI 的「聊天」頁面，選「單一免費 AI」或「多 AI 會診」後，等狀態更新再**手動勾選** `Ollama Cloud`。原有四個模型的預設選取維持不變。
- Ollama Free 方案有少量每月 starter usage credits，並非無限免費。若你的 Ollama 帳戶購買或啟用加值額度，使用此選項可能消耗付費額度；JEI 無法替你強制封鎖 Ollama 帳戶計費，請勿加值或啟用自動購買。
- 不論 Ollama 是否設定，JEI **絕不因其他 AI 失敗而自動切換**到 Ollama，也不切換到 Vercel 付費 AI Gateway。
- 你沒有筆電時也可以使用 Ollama Cloud，但仍需要配置 API Key 與 JEI 私人連線碼；API Key 未配置時，Ollama 按鈕顯示不可用。
- 將來要接本機 Ollama，需要安全的專用連線／後端代理；不能將未驗證的本機 11434 埠直接暴露到網際網路。
