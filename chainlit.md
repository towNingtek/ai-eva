# AI Eva

工程實驗用 Chatbot — **Chainlit + LangGraph + RAG**。

## 如何使用

- 直接輸入問題，Eva 會用 RAG 檢索相關文件後回答
- 想加知識？把文件丟進 `data/docs/` 然後重跑 `python -m app.rag.ingest`
- 想追 LangGraph 執行過程，點開 message 下方的 **Steps**

## 架構

```
你 ──► Chainlit UI ──► LangGraph: retrieve ──► Chroma
                                   └── generate ──► LLM
```

切換 LLM 後端（OpenAI / Ollama Gateway）只需改 `.env` 的 `OPENAI_API_BASE`。
