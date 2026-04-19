# AI Eva

工程實驗用 Chatbot：**Chainlit + LangGraph + RAG**。
[追蹤 issue](https://github.com/town-intelligent/swarm/issues/151)

## 技術棧

- **UI**: Chainlit（含 Copilot 嵌入模式）
- **Orchestration**: LangGraph (`retrieve → generate`)
- **Vector store**: Chroma（本地持久化在 `data/chroma/`）
- **LLM**: OpenAI（預設）/ 可切換至既有 Ollama Gateway
- **Embedding**: `text-embedding-3-small`

## 目錄結構

```
app/
├── main.py              # Chainlit entrypoint
├── graph.py             # LangGraph 定義
├── settings.py
└── rag/
    ├── ingest.py        # 把 data/docs/ 餵進 Chroma
    └── retriever.py
data/
├── docs/                # 把要 RAG 的文件丟這裡
└── chroma/              # 向量庫（自動建）
public/
└── copilot.html         # Copilot widget 嵌入範例頁
```

## 快速開始

### 1. 設定 env

```bash
cp .env.example .env
# 填入 OPENAI_API_KEY
```

切換到 Ollama Gateway 的話改 `.env`：

```bash
OPENAI_API_KEY=dummy
OPENAI_API_BASE=http://host.docker.internal:8002/v1
LLM_MODEL=openai/gpt-4o
```

### 2. 本機跑（不用 Docker）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 把文件丟到 data/docs/ 後 ingest
python -m app.rag.ingest

# 啟動
chainlit run app/main.py --port 7860
```

開 `http://localhost:7860`。

### 3. Docker Compose

```bash
docker compose up -d --build
docker compose exec ai-eva python -m app.rag.ingest
```

### 4. Copilot 嵌入測試

服務跑起來後，用瀏覽器打開 `public/copilot.html`（在本機或放到其他網站都行），右下角會出現 chat bubble。

嵌入到任何網頁的 snippet：

```html
<script src="https://eva.4impact.cc/copilot/index.js"></script>
<script>
  window.mountChainlitWidget({ chainlitServer: "https://eva.4impact.cc" });
</script>
```

## 部署

`eva.4impact.cc` 是 **A record 直指 cms-server** + **nginx 反向代理** + **Let's Encrypt SSL**（非 Cloudflare Tunnel 路徑）：

```
User ──► eva.4impact.cc (A record) ──► cms-server
                                         └─► nginx (443, SSL)
                                               └─► http://localhost:7860 (Chainlit)
```

Nginx 設定：`/etc/nginx/sites-available/eva.4impact.cc`（已有 WebSocket upgrade headers）

改 port 或 config 後：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Auth

內建 Chainlit password auth（單一 admin 帳號）：

- `.env` 設 `ADMIN_USER` / `ADMIN_PASS` / `CHAINLIT_AUTH_SECRET` → 啟用登入頁
- `ADMIN_PASS` 留空 → 關閉 auth（僅本機 dev）

未來升級可選：
- **OAuth**（GitHub / Google）— 改 `@cl.oauth_callback`
- **Cloudflare Access** — 在 CF Zero Trust 後台建 application，policy 指向 `eva.4impact.cc`，前端程式不用改

## 下一步

- 加 PDF/DOCX 上傳 → 即時 ingest（Chainlit `on_file_upload`）
- 加 LangGraph 條件邊：查不到 → 走外部 Search
- 加 Langfuse 觀測
- 升級 auth 至 OAuth 或 Cloudflare Access
