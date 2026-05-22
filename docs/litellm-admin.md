# LiteLLM Admin UI 操作指南（M2.5）

> 進階運維 — master key 認證、Admin UI、virtual keys、預算管控。
> 為 [#8 roadmap M2.5](https://github.com/towNingtek/ai-eva/issues/8) 的執行紀錄。

## 為什麼要 M2.5

M2 把 LiteLLM 接上後，**任何人能打 `localhost:4000` 都能燒你 OpenAI 額度**。M2.5 加上：

1. **Master key 保護** — 沒 key 一律 401
2. **Admin UI** — 看 cost、log、誤用情況
3. **Virtual keys** — 不同 surface（ai-eva web / LINE bot / cron worker）發不同 key，**單獨追蹤花費 + 各自預算上限**

## 認證模式

| 角色 | 持有 key | 權限 |
|---|---|---|
| **Master key**（`LITELLM_MASTER_KEY`） | `.env` 裡那把 | 所有事，包含發 virtual key |
| **Virtual key**（透過 Admin UI 發） | 各 surface 各持一把 | 只能呼叫 LLM，受預算 / model 限制 |

## 開啟 Admin UI

```
http://localhost:4000/ui
```

帳號密碼：
- **Username**: `admin`
- **Password**: 就是 `LITELLM_MASTER_KEY` 整串（在 `.env` 看）

進去後左側有：
- **Virtual Keys** — 建 / 改 / 砍 key、設預算、設可用 model
- **Test Keys** — 直接測單一 model
- **Spend Tracking** — 看各 key / 各 model 的累計花費
- **Usage** — 用量曲線
- **Models** — 看當前 config 註冊的所有 alias

## 發一把 Virtual Key 給新 surface（例如 LINE bot）

### Option A：UI 操作

1. 左邊 Virtual Keys → **Create New Key**
2. 設定：
   - Key Name: `line-bot`（識別用）
   - Models: 勾選允許用的（`cloud-fast`、`local-cheap`）
   - Max Budget USD: `10`（每月燒到 $10 就停）
   - Reset Budget Duration: `monthly`
   - Rate Limit RPM: `60`（每分鐘最多 60 次）
3. **Create** → 拿到 `sk-xxxxx`
4. 把那把 key 給對應 surface（LINE bot 的 `.env`）

### Option B：API 操作

```bash
KEY=<master_key>
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "models": ["cloud-fast", "local-cheap"],
    "max_budget": 10,
    "duration": "30d",
    "rpm_limit": 60,
    "metadata": {"surface": "line-bot"}
  }'
```

回傳 `key` 欄位就是新 key。

## 整套帳單分離的長相

當 M3 LINE Bot、M4 cron worker 都上後：

```
LITELLM_MASTER_KEY           ← 只放 .env，永遠不對外
  ├─ virtual key: ai-eva-web      $50/月、所有 model
  ├─ virtual key: line-bot         $10/月、限 cloud-fast
  ├─ virtual key: cron-worker      $5/月、限 local-cheap
  └─ virtual key: external-tester  $1/月、給朋友試
```

任一 surface 燒爆預算只影響自己。**這是真實營運才用得到的隔離**。

## 注意事項

- **Master key 寫進 .env、`.env` 已 gitignore** — 不會進 git
- **不要把 master key 給任何下游應用**（包括 ai-eva 自己）— 該用 virtual key
- 目前 ai-eva 暫時用 master key 通行（單一使用者、自用）；M3 加 LINE bot 時改用 virtual key
- LiteLLM DB（postgres）在 `ai-eva-litellm-db` container，volume 是 `ai_eva_litellm_pgdata`，要備份就 dump 這個

## 換 Master Key

如果懷疑 master key 外洩：

```bash
# 1. 產新 key
NEW_KEY="sk-$(openssl rand -hex 24)"

# 2. 改 .env
# 3. 重啟 LiteLLM
docker compose restart litellm

# 4. 全部 virtual key 都還能用（key 自己存在 DB、跟 master 解耦）
# 5. 更新 ai-eva 的 LITELLM_API_KEY 為新 master key（或改成用 virtual key）
docker compose restart ai-eva
```

## 後續

- **M3 LINE Bot 上線時**，發一把 `line-bot` virtual key、設預算
- **M4 Cron worker 上線時**，發一把 `cron-worker` virtual key
- **任何外部 share 用** → 先發一把預算上限低的 key、用完就停
