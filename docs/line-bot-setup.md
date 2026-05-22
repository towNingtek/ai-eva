# LINE Bot Setup（M3）

> 把 ai-eva 開到 LINE 上 — 使用者傳訊息 → AI 回應。Push（主動推播）基礎建設預備好，等 M4 cron worker 接。
> 為 [#8 roadmap M3](https://github.com/towNingtek/ai-eva/issues/8) 的執行紀錄。

## 拓樸

```
[使用者手機 LINE]
   ↓ 加 bot 為好友 / 傳訊息
[LINE 伺服器]
   ↓ HTTPS POST + X-Line-Signature header
[https://eva.4impact.cc/webhook/line]
   ↓ Chainlit 的 FastAPI app（同 :7861）
[app/surfaces/line.py]
   ├─ 簽章驗證（HMAC-SHA256 with channel secret）
   ├─ follow event   → INSERT 進 line_users PG 表
   ├─ unfollow event → 標記 unfollowed_at
   └─ message event  → LiteLLM (LITELLM_LINE_KEY) → reply API
                          ↓
                       OpenAI gpt-4o-mini (預設) / Pi5 Qwen
```

## LINE Developer Console 設定

1. https://developers.line.biz → Provider → 新建 Messaging API channel
2. 設定 → Basic settings：
   - 拿 **Channel secret**
3. 設定 → Messaging API：
   - 發 **Channel access token (long-lived)**
   - Webhook URL: `https://eva.4impact.cc/webhook/line`
   - Use webhook: **Enabled**
   - Auto-reply messages: **Disabled**（不然 LINE 預設的「感謝您」會搶在前面）
   - Greeting messages: 可選

## env vars

```bash
# ai-eva .env
LINE_CHANNEL_SECRET=<from console>
LINE_CHANNEL_ACCESS_TOKEN=<from console>

# 從 LiteLLM Admin UI 或 API 發一把限定 cloud-fast + local-cheap、月預算 $5 的 virtual key
LITELLM_LINE_KEY=sk-xxxxxxxxx
```

發 virtual key（範例指令，beta 跟 stable 各發一把不共用）：

```bash
MASTER_KEY=<from .env LITELLM_MASTER_KEY>
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "models": ["cloud-fast", "local-cheap"],
    "max_budget": 5,
    "duration": "30d",
    "rpm_limit": 60,
    "key_alias": "line-bot-stable",
    "metadata": {"surface": "line-bot"}
  }'
```

## 驗收測試（curl）

```bash
SECRET=$LINE_CHANNEL_SECRET
URL=http://localhost:7860/webhook/line   # 或 stable: eva.4impact.cc

# 1. 沒簽章 → 403
curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL -d '{"events":[]}'

# 2. 假簽章 → 403
curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL \
  -H "x-line-signature: bad" -d '{"events":[]}'

# 3. 正確簽章 + 空 events → 200
BODY='{"events":[]}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)
curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL \
  -H "x-line-signature: $SIG" -d "$BODY"

# 4. 假 follow event → 200，並進 PG
BODY='{"events":[{"type":"follow","source":{"userId":"Utest1","type":"user"}}]}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)
curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL \
  -H "x-line-signature: $SIG" -d "$BODY"

# 看 PG
docker exec ai-eva-postgres psql -U chainlit -d chainlit \
  -c "SELECT user_id, followed_at, unfollowed_at FROM line_users;"
```

## 從手機實測

1. LINE Console Messaging API 頁面有 QR code，掃描加 bot 為好友
2. 加完應該在 PG `line_users` 看到 follow event 紀錄
3. 傳訊息「你好」→ 10 秒內收到 OpenAI gpt-4o-mini 回應
4. LiteLLM Admin UI (`http://localhost:4001/ui` for stable) → Spend Tracking → `line-bot-stable` key 的累計 cost 增加

## 已踩過的坑

- **Auto-reply 沒關** → 你的 reply 會被 LINE 預設「感謝您加為好友」搶先送出。Console 一定要關掉 auto-reply
- **Webhook 不能用 HTTP**（LINE 強制 HTTPS） → stable 走 nginx + Let's Encrypt 自動解決；beta 要用 Cloudflare tunnel
- **Channel secret 跟 access token 是兩個不同欄位**，別搞混（secret 短 32 字元；token 很長一串）
- **`reply_token` 只能用一次**，30 秒內 reply 否則失效

## Push（主動推播）— M3 預備好給 M4 用

```python
# app/surfaces/line.py 有
async def push_to_user(user_id: str, text: str) -> bool: ...
```

M4 cron worker 流程會是：

```python
from app.surfaces.line import push_to_user
import asyncpg

# 1. 從 PG 拿要 push 的 user list
conn = await asyncpg.connect(pg_url)
rows = await conn.fetch("SELECT user_id FROM line_users WHERE unfollowed_at IS NULL")

# 2. 推給每一個
for r in rows:
    await push_to_user(r["user_id"], "🌅 早安！今天 GitHub 摘要：...")
```

M3 本身**不主動 push**，只把基礎建設打好。

## 後續

- **M3.1**（之後）：從 LINE 觸發工具（`/search xxx` → web_search、`/compare` → hello_world）
- **M3.2**（之後）：多 LINE channel + 多 virtual key，每個給不同客戶 / 不同 preset
- **M4**：cron + RabbitMQ → push 出去
