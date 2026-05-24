# M4 — Pi5 cron + RabbitMQ → LINE push

> 第一條主動推播鏈路：Pi5 每天 09:00 跑 Qwen 寫早安 → publish 到 RabbitMQ → ai-eva consumer → LINE push 給使用者。
> Roadmap [#8](https://github.com/towNingtek/ai-eva/issues/8) M4。

## 拓樸

```
[Pi5（家裡）]                                        [cms-server（GCP）]
 cron 09:00 daily                                    
   ↓                                                 
 /home/yillkid/eva-worker/eva_daily.py               
   ├─ load env (.env in same dir)                    
   ├─ qwen_chat() → 本機 Ollama Qwen 2.5:3b          
   │    "請寫早安鼓勵..."                            
   ├─ pika.BlockingConnection                        
   │    via Tailscale 100.66.105.30:5673             
   └─ basic_publish queue=line-push                   ┌────────────────────────────┐
                                                  ────│ ai-eva-rabbitmq-stable     │
                                                      │ container :5673:5672       │
                                                      │ user evapush               │
                                                      │ queue line-push (durable)  │
                                                      └────┬───────────────────────┘
                                                           │
                                                           ↓ aio-pika subscribe
                                                      ┌────────────────────────────┐
                                                      │ ai-eva-stable container    │
                                                      │  app/surfaces/queue_consumer.py
                                                      │  ↓ 解析 {user_id, text}    │
                                                      │  ↓ push_to_user(...)       │
                                                      └────┬───────────────────────┘
                                                           ↓ LINE Messaging API
                                                      [使用者手機 LINE]
```

## 元件清單

| 位置 | 元件 | 角色 |
|---|---|---|
| Pi5 | `~/eva-worker/eva_daily.py` | cron 觸發的 producer |
| Pi5 | `~/eva-worker/.env` | RABBITMQ_URL / PUSH_USER_ID（不進 git） |
| Pi5 | `crontab` | `0 9 * * * /usr/bin/python3 ~/eva-worker/eva_daily.py` |
| cms-server beta | `ai-eva-rabbitmq` (:5672 / :15672) | beta 環境 RabbitMQ |
| cms-server stable | `ai-eva-rabbitmq-stable` (:5673 / :15673) | **prod**，cron 推這 |
| ai-eva 兩邊 | `app/surfaces/queue_consumer.py` | aio-pika consumer，啟動時 fire-and-forget |

## env vars

### Pi5 `~/eva-worker/.env`
```bash
RABBITMQ_URL=amqp://evapush:<STABLE_PASS>@100.66.105.30:5673/
RABBITMQ_QUEUE=line-push
PUSH_USER_ID=U....               # 你的 LINE userId
```

### ai-eva container（兩個環境各設）
```bash
RABBITMQ_USER=evapush
RABBITMQ_PASS=<env-specific>
RABBITMQ_URL=amqp://evapush:<env-specific>@rabbitmq:5672/  # 容器內網
RABBITMQ_QUEUE=line-push
```

## 為什麼 Pi5 看到 cms-server 是 :5673（而不是 :5672）

- Beta rabbitmq 占了 cms-server host 的 :5672
- Stable override 把它擠到 :5673
- 兩個都對 Tailscale 開放
- Cron worker 推 prod（stable）→ 5673

如果之後要在 beta 測 cron：改 Pi5 `.env` 把 URL port 改成 5672 + 用 beta 的 password。

## 手動觸發測試

```bash
# Pi5 上
python3 ~/eva-worker/eva_daily.py
```

預期：
1. 印 pika 連線成功
2. 印 "published N chars to queue=line-push"
3. **2-3 秒內你 LINE 收到 Qwen 寫的早安**

如果 LINE 沒收到：
- 看 `ai-eva-stable` 容器 log（`docker logs ai-eva-stable | grep queue`）— 有沒有看到「push (src=pi5-eva-daily)」
- 看 RabbitMQ 管理頁 http://localhost:15673（admin / evapush + master pass）— queue depth 是不是堆積
- 看 LINE webhook log — push API 是不是 200

## 為什麼 RabbitMQ 不用 host network

- LiteLLM 要打 Pi5 Tailscale IP 100.74.6.41 → 需要 host network
- RabbitMQ 反過來：Pi5 打 cms-server，cms-server 用 ports forwarding 暴露 5673/15673
- bridge mode + ports 即可，比 host 乾淨

## 後續方向

- **M3 session 進來後**：cron push 帶 session_id metadata、push 完不會被當「對話的一部分」誤吃進 context
- **多個 cron 任務**：在 Pi5 同 directory 加 `eva_weekly.py` / `eva_alert.py`，各自 crontab 行
- **多個 user**：cron script 改成查 PG `line_users` 表所有 active user、逐個 push
- **失敗重試 / dead letter**：RabbitMQ 預設沒 DLQ，要加得寫 retry policy
- **看 cost**：LiteLLM Admin UI 看每個 virtual key 累計 — 但 cron 走 Pi5 不耗 LiteLLM 預算

## 已踩過的坑

- **Stable 的 docker-compose.yml 跟 beta 同步**：直接 `cp beta → stable`（git 同步前的人工搬）
- **第一次 RabbitMQ 拉 image 慢**：~10 秒，consumer 啟動會 retry 重連、不要慌
