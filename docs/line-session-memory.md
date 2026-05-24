# LINE Session Memory（Phase 1）

> LINE bot 從 stateless 升級成「對話式記憶」：每位 user 進來開 session，記 12 輪 context；30 min idle 自動結束、push 告別。
> 設計來源：[虎科大 ch5 LINE Bot 對話記憶](https://hackmd.io/@yillkid/rk_kVbxlfl)（同台機器 `4-learn/rag-kit/apps/huwei_landmarks/`），抄出來改 LiteLLM + asyncpg。

## 拓樸

```
LINE 使用者
   ↓ HTTPS
beta-eva.4impact.cc / eva.4impact.cc   ← Cloudflare Tunnel
   ↓
ai-eva container :7860
   ├─ /webhook/line             收 LINE event
   │    ├─ end keyword？        → end_session + reply 告別
   │    └─ 一般文字             → session.chat() → reply
   └─ /tasks/scan-timeouts      scan_timeouts() + push 告別
        ↑
session-scanner sidecar
   每 60s curl POST + X-Scan-Token
        ↓
PG (ai-eva-postgres)
   line_sessions          ┐ 兩張新表（跟 chainlit 既有 thread/users 並存）
   line_session_messages  ┘
```

## 兩張表

| 表 | 欄位 | 用途 |
|---|---|---|
| `line_sessions` | `id / user_id / started_at / last_message_at / ended_at / end_reason / summary` | 一筆 = 一段對話。`ended_at IS NULL` 即 active |
| `line_session_messages` | `id / session_id / role / content / created_at` | role = `user` / `assistant`，按 id 排序組 context |

啟動時 `ensure_session_tables()` 自動 `CREATE TABLE IF NOT EXISTS`，不用 alembic。

## 對話流程（happy path）

1. user 傳訊：`你好`
2. `line.py /webhook/line` → `_handle_event` text 分支
3. 非 end keyword → `line_session.chat(user_id, text)`：
   - 撈 active session（沒有就 `start_session`）
   - `INSERT user message` + 更新 `last_message_at`
   - 撈最近 12 則歷史
   - `messages = [system_prompt] + history` → `make_llm(api_key=LITELLM_LINE_KEY).ainvoke(...)`
   - `INSERT assistant message` + 回傳 reply
4. `_line_reply(reply_token, answer)`

## 結束（兩種）

### A. 使用者自己喊結束（reply 模式）

End keywords：`bye / Bye / BYE / end / End / /end / /bye / 再見 / 掰掰 / 結束 / 結束對話 / 下次見`

webhook 內：
- `line_session.is_end_keyword(text)` → True
- `end_session(sess.id, "user")` 
- `_line_reply(reply_token, GOODBYE_USER_INITIATED)` ← 用 reply token（免費 quota）

### B. Idle 30 min（push 模式）

`session-scanner` sidecar 每 60s POST `/tasks/scan-timeouts`：
- `scan_timeouts()` 一個 UPDATE 同時 mark ended + return 逾時的 (id, user_id)
- 對每筆 `push_to_user(user_id, GOODBYE_TIMEOUT)` ← push API（吃 quota，但是 user 已沒在線、沒 reply token 可用）

## env vars

| Key | 預設 | 說明 |
|---|---|---|
| `SESSION_SCAN_TOKEN` | （必填）| sidecar curl 戳 `/tasks/scan-timeouts` 用的 `X-Scan-Token`；沒設 endpoint 直接 503 |
| `SESSION_TIMEOUT_MINUTES` | `30` | idle 多久算逾時 |
| `SESSION_CONTEXT_TURNS` | `12` | LLM context 最多塞幾則歷史 |
| `LITELLM_LINE_KEY` | （沿用 M3）| LINE bot 專用 virtual key，session.chat() 走這把算錢 |

## docker-compose 新增 service

```yaml
session-scanner:
  image: curlimages/curl:8.10.1
  depends_on: [ai-eva]
  environment:
    SESSION_SCAN_TOKEN: ${SESSION_SCAN_TOKEN}
  entrypoint: ["sh", "-c"]
  command:
    - |
      while true; do
        curl -fsS -X POST http://ai-eva:7860/tasks/scan-timeouts \
          -H "X-Scan-Token: $$SESSION_SCAN_TOKEN" \
          >/dev/null 2>&1 || true
        sleep 60
      done
```

走 docker compose network 內網 `http://ai-eva:7860`、不對外暴露。`||true` 避免 ai-eva 重啟期間 curl 失敗讓 sidecar exit。

## 手動驗證

```bash
# 1. sidecar 戳得通 → expect "ended:0, pushed:0"
docker exec ai-eva-session-scanner sh -c \
  'curl -s -X POST http://ai-eva:7860/tasks/scan-timeouts \
     -H "X-Scan-Token: $SESSION_SCAN_TOKEN"'

# 2. 沒 token 直接擋
curl -s -X POST http://localhost:7860/tasks/scan-timeouts   # expect 503

# 3. 錯 token 擋
curl -s -X POST http://localhost:7860/tasks/scan-timeouts \
  -H "X-Scan-Token: wrong"                                  # expect 403

# 4. LINE 端：傳「你好」→ 回覆有印象，連續對話 LLM 看得到前一句
# 5. 傳「bye」→ 收到 GOODBYE_USER_INITIATED + 下一句重啟 session
# 6. 不要互動 31 分鐘 → 收到 GOODBYE_TIMEOUT (push)
```

PG 端確認：
```sql
SELECT user_id, COUNT(*) FILTER (WHERE ended_at IS NULL) AS active,
       COUNT(*) AS total
FROM line_sessions GROUP BY user_id;

SELECT session_id, role, left(content, 40) FROM line_session_messages
ORDER BY id DESC LIMIT 20;
```

## 後續

- **Phase 2**：summary 欄目前都 NULL；end 時可以 call LLM 寫一句總結存起來，給「之前我們聊過 X」用
- **跨 surface 共用**：把 session memory 拉成 `app/memory/` 模組，Chainlit web `on_message` 也可吃同樣的記憶
- **管理介面**：admin hub 加 `/admin/sessions` 看 active / 結束統計
