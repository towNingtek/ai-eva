# LiteLLM Gateway Setup（M2 紀錄）

> 把 ai-eva 從「直連 OpenAI」改成「全部走 LiteLLM proxy」。LiteLLM 路由到 OpenAI（雲端互動主線）或 Pi5 Ollama（本地省錢節點），失敗自動 fallback。
> 為 [#12](https://github.com/towNingtek/ai-eva/issues/12) 的執行紀錄。

## 拓樸

```
[ai-eva container]
  langchain_openai.ChatOpenAI(base_url="http://host.docker.internal:4000/v1")
       ↓
[ai-eva-litellm container] (host network mode)
  /v1/chat/completions  ──── alias 路由 ────┐
                                          │
       ┌──────────────── openai/gpt-4o-mini (cloud-fast / default)
       │                       ↓
       │                  api.openai.com
       │
       └──────────────── ollama_chat/qwen2.5:3b (local-cheap)
                              ↓ via Tailscale mesh VPN
                         http://100.74.6.41:11434 (Pi5)
                              ↓
                         Ollama → Qwen 2.5:3b-q4
```

## 三個 model 別名

`litellm-config.yaml`：

| alias | 對應 provider/model | 用途 |
|---|---|---|
| `cloud-fast` | `openai/gpt-4o-mini` | 互動主線、品質高、快 |
| `local-cheap` | `ollama_chat/qwen2.5:3b-instruct-q4_K_M` (Pi5) | 被動推播、預處理節點、省 OpenAI 額度 |
| `default` | `openai/gpt-4o-mini` | 沒指定 model 的 client 用 |

Router fallback：`local-cheap` 失敗 → 自動回 `cloud-fast`（驗證過：停 Pi5 ollama，使用者依然有回應）。

## 重要設定點

### docker-compose litellm service

```yaml
litellm:
  image: ghcr.io/berriai/litellm:main-stable
  network_mode: host             # ← 為了打 Pi5 Tailscale IP
  environment:
    OPENAI_API_KEY: ${OPENAI_API_KEY}
  volumes:
    - ./litellm-config.yaml:/app/config.yaml:ro
  command: ["--config", "/app/config.yaml", "--port", "4000"]
```

**注意**：**不要** `env_file: - .env`。否則 LiteLLM 會 inherit Chainlit 的 `DATABASE_URL`，把 prisma migrate 跑進 Chainlit 的 PG，污染對方 schema。

### `network_mode: host` 為什麼必要

LiteLLM 要打 Pi5 Tailscale IP `100.74.6.41`。如果 LiteLLM 在 docker bridge 網路（預設），bridge 不在 Tailscale 的 routing table 上，會打不到。host network 直接共用 cms-server 的網路 stack，跟 host 一樣能走 Tailscale。

### ai-eva 端設定

```python
# app/settings.py
LITELLM_API_BASE = os.getenv("LITELLM_API_BASE", "http://host.docker.internal:4000/v1")
LITELLM_DEFAULT_MODEL = os.getenv("LITELLM_DEFAULT_MODEL", "cloud-fast")
LITELLM_CHEAP_MODEL = os.getenv("LITELLM_CHEAP_MODEL", "local-cheap")

# app/core/llm.py
def make_llm(*, alias=None, temperature=0.2, streaming=True):
    return ChatOpenAI(
        model=alias or LITELLM_DEFAULT_MODEL,
        api_key="litellm-no-auth",
        base_url=LITELLM_API_BASE,
        ...
    )
```

### 多模型對照（hello_world app）

```python
# app/apps/hello_world/handler.py
_MODELS = [
    ("🟢 OpenAI gpt-4o-mini", None),           # 走預設 cloud-fast
    ("🟡 Pi5 Qwen 2.5:3b",    "local-cheap"),
    # 未來加 Claude / Gemini：先在 litellm-config.yaml 新增 model_name，再加一行
]

# 平行 streaming 兩段 message 給使用者並排比較
await asyncio.gather(*(_stream_one(...) for ...))
```

**model selection 是 node 自己宣告的責任**（非 app 統一硬綁），加新 model 改 list 即可。

> 註：曾短暫嘗試用 rag_chat 的 query_rewrite node 走 Pi5、generate 走 OpenAI 來示範跨 provider，但發現 Pi5 Qwen 對某些議題會偷塞立場（如「台灣是中國的一部分嗎？」被改寫成肯定句），不適合做隱形 query rewrite。已改成把多 provider demo 移到 hello_world app，並把 RAG 移除（2026-05-22）。

## 已踩過的坑（給未來自己）

1. **LiteLLM container 不要 inherit Chainlit 的 .env** — `DATABASE_URL` 會讓它跑 prisma migrate 進錯的 DB。用 `environment:` 顯式列必要 env。
2. **`network_mode: host` 跟 `ports:` 衝突** — host mode 下 published ports 會被忽略（compose 會印 warning）。要嘛 host mode、要嘛 bridge + ports，不能同時。
3. **`api_base` 給 ollama_chat 要寫完整 IP**（如 Tailscale `100.x.y.z:11434`），不要塞 hostname（除非有 DNS 解析能力）。
4. **LiteLLM 啟動慢** — 從 container start 到 port 4000 listen 約 30~50 秒（prisma migrate + module imports）。容器看似活著但 health check 不過是正常，等就好。

## 對 ai-eva 使用者的影響

**前端 UI 零變化**。內部變化：

- 任何 LLM 呼叫都走 LiteLLM，可在 cms-server 後台統一看 log / cost
- 之後想加 Claude / Gemini，只要 `litellm-config.yaml` 多一段、ai-eva 不用改一行
- Pi5 掛了使用者不會中斷服務（自動 fallback）

## 後續里程碑

- **M2.5（可選）**：LiteLLM virtual keys（不同 surface 分流帳單）、預算上限、cost dashboard、多 OpenAI key 負載均衡
- **M3 LINE Bot Adapter**：LINE webhook → 同一個 dispatch → 自動透過 LiteLLM 走 LLM
- **M4 RabbitMQ + 被動推播**：cron worker 也透過 LiteLLM（或直接 call Pi5 ollama，看任務性質）

詳見 [roadmap #8](https://github.com/towNingtek/ai-eva/issues/8)。
