# AI Eva

> 工程實驗用的對話式 AI 平台 — Chainlit + LangGraph + 可插拔 apps。
>
> 中長期演化為個人 / 內部用的 **本地 + 雲端混合 LLM 場域**，搭配 Pi5 hub、LINE bot 推播、模擬感測器，做為日常 AI 工具的「沙盒」。

[相關討論](https://github.com/town-intelligent/swarm/issues/151) ・ [線上 stable](https://eva.4impact.cc)

---

## 與 `LLMTwins` 的關係

`towNingtek/ai-eva` 跟 `towNingtek/LLMTwins` **不合併**，定位不同：

| Repo | 角色 |
|---|---|
| `LLMTwins` | 多 tenant prod 平台（branch-per-tenant，南投縣府 / NTIDIPC / tplanet AI 等） |
| `ai-eva` | LangGraph 實驗 + 個人/內部 chat surface（這個 repo） |

兩者並存、互不取代。

---

## 系統架構

```mermaid
flowchart TB
    subgraph Surface["使用者介面層"]
        Web["Chainlit Web<br/>(深度配置 / 文件 / 開發)"]
        LINE["LINE Bot<br/>(日常對話 / 推播接收)<br/>(roadmap)"]
        Discord["Discord<br/>(devops 通知)<br/>(roadmap)"]
    end

    subgraph Eva["AI-Eva 核心"]
        Dispatch["on_message dispatch"]
        Registry["apps/_registry<br/>自動發現"]
        Apps["Apps<br/>plain_chat (default)<br/>web_search / hello_world / ..."]
    end

    subgraph LLM["LLM 抽象層"]
        LiteLLM["LiteLLM proxy<br/>OpenAI-spec gateway"]
        OpenAI["OpenAI / Anthropic / Gemini<br/>(雲端，互動主線)"]
        PiLLM["Pi5 Ollama<br/>Qwen 2.5:3b-q4<br/>(本地，被動推播 + 省錢節點)"]
    end

    subgraph Net["網路通道"]
        Tailscale["Tailscale mesh VPN<br/>cms-server ↔ Pi5"]
        CFTunnel["Cloudflare Zero Trust Tunnel<br/>SSH 管理用"]
    end

    subgraph Async["非同步 / 推播"]
        RMQ["RabbitMQ<br/>(roadmap)"]
        Cron["Pi5 cron worker<br/>(daily summary, anomaly)<br/>(roadmap)"]
        Sim["模擬感測 + LightGBM<br/>(roadmap)"]
    end

    subgraph Store["資料"]
        PG[(Postgres<br/>threads / users)]
    end

    Web --> Dispatch
    LINE -.-> Dispatch
    Discord -.-> RMQ

    Dispatch --> Registry --> Apps
    Apps --> LiteLLM
    LiteLLM --> OpenAI
    LiteLLM --> PiLLM
    LiteLLM --- Tailscale
    Tailscale --- PiLLM

    Apps --> PG

    Sim -.-> Cron
    Cron -.-> LiteLLM
    Cron -.-> RMQ
    RMQ -.-> LINE
    RMQ -.-> Discord

    CFTunnel -.- PiLLM
```

實線 = 現況；虛線 = roadmap（見下方）。

---

## 技術棧

| 層 | 技術 |
|---|---|
| UI | **Chainlit 2.x**（含 commands、chat profiles、auth、data layer、streaming） |
| Orchestration | **LangGraph** — 各 app 自己組（簡單應用用 `asyncio.gather` 也行） |
| LLM provider 抽象 | **LiteLLM proxy**（M2）— 統一 OpenAI-spec、路由到 OpenAI / Pi5 Ollama / 未來 Claude / Gemini |
| LLM 雲端 | OpenAI gpt-4o-mini（預設 alias `cloud-fast`） |
| LLM 本地 | Pi5 Ollama + Qwen 2.5:3b-q4（alias `local-cheap`，via Tailscale） |
| 私網 | **Tailscale mesh VPN** — cms-server ↔ Pi5 走加密私網，繞開 Cloudflare HTTP 100s 限制 |
| Web search | Tavily（主） → DuckDuckGo（自動降級） |
| Chat history | Postgres + `SQLAlchemyDataLayer` |
| Blob storage | `LocalStorageClient`（檔案存於 `public/elements/`） |

---

## 目錄結構

```
app/
├── main.py                # Chainlit entrypoint + dispatch
├── settings.py
├── core/
│   ├── llm.py             # ChatOpenAI(base_url=litellm)，接收 alias 參數
│   ├── search.py          # Tavily + DDG fallback
│   └── storage.py         # LocalStorageClient（Chainlit data layer 用）
└── apps/                  # 可插拔子應用
    ├── _registry.py       # 自動發現、註冊到 Chainlit commands
    ├── plain_chat/        # 預設 — 純對話（單一 OpenAI call）
    ├── web_search/        # 🌐 網頁搜尋（Tavily → DDG fallback）
    └── hello_world/       # 🪞 模型對照（同題並行打多家模型）
litellm-config.yaml        # LiteLLM 路由設定（alias → provider/model）
public/
└── elements/              # Chainlit 上傳檔案 blob
```

---

## 快速開始（local dev）

### 1. 設定 env

```bash
cp .env.example .env
# 填 OPENAI_API_KEY、ADMIN_PASS、TAVILY_API_KEY 等
```

### 2. Docker compose

```bash
docker compose up -d --build
```

開 `http://localhost:7860`。

### 3. 加新 LangGraph app（30 秒）

```bash
mkdir app/apps/your_app
# meta.py
cat > app/apps/your_app/meta.py <<'EOF'
META = {
    "id": "your_app",
    "label": "你的工具",
    "icon": "✨",
    "cl_icon": "Sparkles",       # Lucide 名稱
    "is_default": False,
    "show_in_menu": True,
    "description": "一句話描述",
}
EOF

# handler.py — async def handle(payload: str, msg: cl.Message) -> None
# 自己寫 LangGraph
```

容器重啟 → `_registry.discover()` 自動掃到 → Chainlit 工具選單多一個。**完全不用改 `main.py`**。

---

## 部署（雙工作樹）

| 環境 | 本機路徑 | Branch | Container | Port | URL |
|---|---|---|---|---|---|
| beta | `~/workspace/towningtek/beta/ai-eva` | `beta` | `ai-eva` | 7860 | （localhost-only） |
| stable | `~/workspace/towningtek/stable/ai-eva` | `main` | `ai-eva-stable` | 7861 | [eva.4impact.cc](https://eva.4impact.cc) |

### 開發鐵則

1. 永遠在 **beta** 工作樹 + `beta` 分支上開發
2. `commit` → `push origin beta` → `gh pr create --base main --head beta`
3. PR merge 後，stable 工作樹執行 `git pull origin main`
4. **Rebuild stable 容器**（千萬別漏這步，否則 main 有 code 但 stable 沒跑）：

```bash
cd ~/workspace/towningtek/stable/ai-eva
docker compose -p ai-eva-stable build ai-eva
docker compose -p ai-eva-stable up -d --no-deps ai-eva
```

- 必須 `-p ai-eva-stable` 專案名
- `build` 跟 `up` 分兩步執行，避免 container_name 衝突
- `--no-deps` 避免動到 postgres（曾踩過 stable postgres 被改名的坑）

### Stable 站獨有檔案（不進 git）

- `.env` — 環境變數
- `docker-compose.override.yml` — container_name 加 `-stable` 後綴、port 7861

兩者都已加進 `.gitignore`。

---

## Roadmap：擴張為實驗場域

短中期目標是把現有 Chainlit chat surface 擴成「本地 + 雲端混合 LLM 場域」，含 LINE 推播、Pi5 hub、模擬感測，當作日常 AI 工具的沙盒。

### 里程碑（順序為相依性，非時間表）

| # | 里程碑 | 主要產出 | 狀態 |
|---|---|---|---|
| **M1** | **Pi5 Hub 設置** | Pi5 + Ollama + Qwen 2.5:3b-q4 + Cloudflare Zero Trust SSH | ✅ [#9](https://github.com/towNingtek/ai-eva/issues/9) |
| **M2** | **LiteLLM 接通** | LiteLLM proxy + Tailscale 連 Pi5；ai-eva 全走 LiteLLM；hello_world 改成多模型對照 demo | ✅ [#12](https://github.com/towNingtek/ai-eva/issues/12) |
| M2.5 | *(可選)* LiteLLM 進階運維 | virtual keys / 預算 / multi-key 負載均衡 / cost dashboard | 視 M3 需求啟動 |
| M3 | **LINE Bot Adapter** | LINE Messaging API webhook → Chainlit FastAPI app → 同一個 dispatch | |
| M4 | **第一條被動推播 graph** | Pi5 cron + RabbitMQ → LINE push（daily summary） | |
| M5 | **模擬感測 + 異常預警** | LightGBM 預測（參考 [Pi5 IoT-LLM 文章](https://cheng-min-i-taiwan.blogspot.com/2026/05/usr-5-iot-llm.html)）→ Qwen 解讀 → LINE push | |
| M6 | **Web Admin UI**（甜點，最後做） | *可能大幅縮減* — LiteLLM 自帶 key/cost/log UI；剩下只有 ai-eva 自家「app 啟用 / 使用者權限」 | |

每個里程碑對應一個 GitHub milestone，下面再切細 issue。詳見 [roadmap tracking issue #8](https://github.com/towNingtek/ai-eva/issues/8)。

### 關鍵架構決策

- **LLM 抽象用 LiteLLM**（不自寫 router）— 業界事實標準、OpenAI-spec、內建 fallback / cost / virtual keys
- **Pi5 ↔ cms-server 走 Tailscale**（不走 Cloudflare HTTP）— Cloudflare 100s timeout 對長 LLM 生成不安全；Tailscale mesh VPN 無時限
- **Cloudflare Zero Trust Tunnel** 限定**管理面**使用（`ssh pi5`），不做工作流量

### 範圍宣告（避免 scope creep）

- 🎯 **個人 / 內部工程實驗用**，**不打算產品化**
- 🎯 **單一中央 Pi5 hub**，不做 per-device edge
- 🎯 寵物 / 養殖那類「電子雞」情境用 **LINE chat + 模擬資料** 達成，**不做真實硬體**
- ❌ 不做多租戶（多租戶有 `LLMTwins` 在做）
- ❌ 不做 mobile native app

### Protocol 分工

| 場景 | 協定 |
|---|---|
| Browser ↔ Chainlit | WebSocket（Chainlit 內建） |
| ai-eva ↔ LiteLLM | HTTP（OpenAI-spec `/v1/chat/completions`） |
| LiteLLM ↔ Pi5 Ollama | HTTP / Tailscale 私網（內部 Ollama-spec 或 OpenAI-compat） |
| cms-server ↔ Pi5 管理 | SSH over Cloudflare Zero Trust（`ssh pi5`） |
| Service ↔ Service 非同步 | RabbitMQ |
| 未來 IoT device ↔ Hub | MQTT |

---

## Auth

內建 Chainlit password auth（單一 admin），由 `.env` 控制：

- `ADMIN_PASS` 留空 → 關閉 auth（僅本機 dev）
- 有值 → 啟用登入頁

升級路徑（roadmap）：

- **Cloudflare Access**（最省心）— 在 eva.4impact.cc 前面套 SSO，app 程式碼不動
- **OAuth**（GitHub / Google）— `@cl.oauth_callback`
- **DB 用戶表** — 改 `auth_callback` 查 Postgres `users` 表

---

## 貢獻 / 故障排查

- Issue tracker: [github.com/towNingtek/ai-eva/issues](https://github.com/towNingtek/ai-eva/issues)
- 已知坑：見 closed issues #1 ~ #6
- 切記：**stable rebuild 時 build 跟 up 分兩步 + `--no-deps`**（不照做 stable PG 會被改名）
