# Eva Admin Hub（運維入口）

> 把 RabbitMQ / LiteLLM 管理 UI、ai-eva 站點等所有運維 surface 收進一個 SSO 後台、避免每次都得 SSH tunnel。

## 拓樸

```
你瀏覽器 (任何地方)
   ↓
Cloudflare Access SSO（OTP 或 Google login，policy = me 白名單）
   ↓
Cloudflare Tunnel "tplanet-4impact"
   ↓
       eva-admin.4impact.cc      → nginx → /var/www/eva-admin (landing)
       eva-rabbitmq.4impact.cc   → :15673 (stable RabbitMQ Mgmt)
       eva-litellm.4impact.cc    → :4001  (stable LiteLLM Admin UI)
```

Beta 環境（:5672 RabbitMQ / :4000 LiteLLM）刻意**不對外**、用 SSH tunnel 進，避免 dev 場域被誤用。

## 五個 surface 對應 URL

| URL | 後端 | 認證 |
|---|---|---|
| `https://eva-admin.4impact.cc` | nginx 靜態 landing page | Cloudflare Access |
| `https://eva-rabbitmq.4impact.cc` | `localhost:15673` RabbitMQ Mgmt UI | CF Access + RabbitMQ user/pass |
| `https://eva-litellm.4impact.cc/ui` | `localhost:4001/ui` LiteLLM Admin UI | CF Access + master key |
| `https://eva.4impact.cc` | `localhost:7861` ai-eva stable（既有） | Chainlit password auth |
| `https://beta-eva.4impact.cc` | `localhost:7860` ai-eva beta（既有） | Chainlit password auth |

## 部署清單（給未來自己 / 從零重建）

### 1. DNS

3 個 CNAME 指 tunnel（proxied=true、TTL auto）：

| name | target |
|---|---|
| `eva-admin` | `c962e3fc-1501-414a-9f5d-76efa549072a.cfargotunnel.com` |
| `eva-rabbitmq` | 同上 |
| `eva-litellm` | 同上 |

用 Cloudflare DNS API（需 Zone:DNS:Edit 權限）：

```bash
CF=<api_token>
ZONE=1394ee0496f8ebaa30ba9a33155809d5    # 4impact.cc
TARGET="c962e3fc-1501-414a-9f5d-76efa549072a.cfargotunnel.com"
for name in eva-admin eva-rabbitmq eva-litellm; do
  curl -s -X POST -H "Authorization: Bearer $CF" -H "Content-Type: application/json" \
    "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records" \
    -d "{\"type\":\"CNAME\",\"name\":\"$name\",\"content\":\"$TARGET\",\"proxied\":true,\"ttl\":1}"
done
```

### 2. Cloudflare Tunnel ingress

加進 `/etc/cloudflared/config.yml`（在 `# AI Eva BETA` 上方插入）：

```yaml
# AI Eva Admin Hub (Phase 1)
- hostname: eva-admin.4impact.cc
  service: http://localhost:80
- hostname: eva-rabbitmq.4impact.cc
  service: http://localhost:15673
- hostname: eva-litellm.4impact.cc
  service: http://localhost:4001
```

完整片段見 `ops/eva-admin/cloudflared-ingress.snippet.yaml`。

```bash
sudo systemctl restart cloudflared
```

### 3. Nginx landing page

```bash
sudo mkdir -p /var/www/eva-admin
sudo cp ops/eva-admin/index.html /var/www/eva-admin/
sudo cp ops/eva-admin/eva-admin.4impact.cc.nginx.conf /etc/nginx/sites-available/eva-admin.4impact.cc
sudo ln -sf /etc/nginx/sites-available/eva-admin.4impact.cc /etc/nginx/sites-enabled/eva-admin.4impact.cc
sudo nginx -t && sudo systemctl reload nginx
```

### 4. Cloudflare Access Application

用 API（需 Account:Cloudflare One: Apps:Edit + Access:IdP:Edit 權限）：

```bash
CF=<api_token>
AID=58fc30c9c529515be7c65b903d70fbc3   # Yillkid@gmail.com's Account

# 建 application
curl -s -X POST -H "Authorization: Bearer $CF" -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/$AID/access/apps" \
  -d '{
    "name": "Eva Admin Hub",
    "type": "self_hosted",
    "domain": "eva-admin.4impact.cc",
    "self_hosted_domains": [
      "eva-admin.4impact.cc",
      "eva-rabbitmq.4impact.cc",
      "eva-litellm.4impact.cc"
    ],
    "session_duration": "24h"
  }'
# 拿回的 id → APP_ID

# 建 policy（白名單三個 email）
curl -s -X POST -H "Authorization: Bearer $CF" -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/$AID/access/apps/$APP_ID/policies" \
  -d '{
    "name": "me",
    "decision": "allow",
    "include": [
      {"email": {"email": "yillkid@gmail.com"}},
      {"email": {"email": "townintelligent@gmail.com"}},
      {"email": {"email": "jyun-yu@4impact.cc"}}
    ]
  }'
```

或在 UI 操作（一次性 token 用完就撤銷）：
- https://one.dash.cloudflare.com/58fc30c9c529515be7c65b903d70fbc3/access/apps
- Add an application → Self-hosted → 三個 hostname 一次加 → Policy 三個 email

### 5. 驗證

| 測試 | 預期 |
|---|---|
| `curl https://eva-admin.4impact.cc` | Cloudflare Access 登入頁（HTML 含 `cloudflare access`） |
| 瀏覽器登入後開 `eva-admin.4impact.cc` | 看到黑底 Eva Admin Hub landing |
| 點 LiteLLM 連結 | 跳到 `eva-litellm.4impact.cc/ui` 看到 LiteLLM 登入 |
| 點 RabbitMQ 連結 | 跳到 `eva-rabbitmq.4impact.cc` 看到 RabbitMQ Mgmt 登入 |

## 已踩過的坑

- **OTP 不到 Gmail**：Cloudflare Access 預設只給 onetimepin IdP，OTP 容易被 Gmail spam 過濾。**用公司 email**（`jyun-yu@4impact.cc`）登入比較穩；長期想無痛 SSO 要在 Cloudflare 額外設 Google IdP（要 GCP OAuth client）
- **Path-based proxy 跟 subdomain 比**：RabbitMQ + LiteLLM hardcoded asset path、用 subdomain 直 proxy 最穩、path 模式會 debug 到死
- **DNS:Edit / Access:Apps:Edit 是兩種 token 權限**：要分開檢查、別用 Global API Key（高風險）
- **Beta admin 不對外**：避免開發環境 cost / queue 被外界看到、開發者自己 SSH tunnel 即可

## Beta 環境 admin（SSH tunnel 模式）

```bash
# Mac 上跑
ssh -L 4000:localhost:4000 -L 15672:localhost:15672 gcp

# 瀏覽器
http://localhost:4000/ui    # Beta LiteLLM
http://localhost:15672      # Beta RabbitMQ Mgmt
```

## 後續

- **Phase 2**：自家「使用者 / app 管理 UI」— 等真有多 user 才動
- **Google SSO IdP**：GCP Console 建 OAuth client、Cloudflare Access 加 IdP、policy 加上 Google login
- **更多 surface**：之後加 pgAdmin / Grafana 等就照 step 1-4 流程加新 hostname
