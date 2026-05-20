# Pi5 Hub Setup 備忘

> 把 Raspberry Pi 5 (8GB) 裝成中央 worker hub（Ollama + Docker + Cloudflare Zero Trust SSH）。
> 為 [#9](https://github.com/towNingtek/ai-eva/issues/9) 的執行紀錄。

## 機器資訊

| 項目 | 值 |
|---|---|
| 機型 | Raspberry Pi 5（8GB） |
| OS | Raspberry Pi OS (64-bit) Lite — Debian 12 |
| Kernel | `6.12.75+rpt-rpi-2712` aarch64 |
| Hostname | `pi5` |
| 一般使用者 | `yillkid` |
| LAN IP | `192.168.0.138`（WiFi DHCP — 路由器後台可固定） |

## 對外存取

走 **Cloudflare Zero Trust Tunnel + Access SSH**（不是 Pi4 那種 reverse SSH）。

| 來源 | 指令 | 走法 |
|---|---|---|
| Mac | `ssh pi5` | `~/.ssh/config` 加 `Host pi5` + `cloudflared access ssh` |
| cms-server (GCP) | `ssh pi5` | 同上，已加進 `~/.ssh/config` |
| 任何裝 cloudflared 的機器 | 同 | 只要該帳號有 Cloudflare Access 政策授權 |

Cloudflare 對外 hostname：`pi5-ssh.4impact.cc`。

### SSH config snippet（給其他機器抄）

```
Host pi5
    HostName pi5-ssh.4impact.cc
    User yillkid
    ProxyCommand cloudflared access ssh --hostname %h
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking accept-new
```

## 安裝清單

| 元件 | 版本 | systemd | 用途 |
|---|---|---|---|
| `cloudflared` | 2026.5.0 | enabled | SSH tunnel 到 Cloudflare 邊緣 |
| `docker` | 29.5.1 | enabled | 容器執行環境（M4 RabbitMQ / worker pipeline 會用） |
| `ollama` | 0.24.0 | enabled | 本地 LLM 推論服務 |
| `qwen2.5:3b-instruct-q4_K_M` | （ollama model） | — | 主力小模型，被動推播任務用 |

## Ollama 設定

預設綁 `127.0.0.1`，已改成 `0.0.0.0`（為了之後 cms-server 透過 Tailscale 或 LAN 直接呼叫）。

```
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

`OLLAMA_HOST=0.0.0.0:11434` 在受信任的 LAN / VPN 內 OK；對外曝光前**務必加防火牆或 Tailscale-only 規則**。

## 已踩過的坑（給未來自己）

1. **`curl -fsSL https://ollama.com/install.sh | sh` 會卡在 ARM64 tarball 下載**（同時兩次執行甚至會起兩個並行 curl）
   - 解法：binary 已經到位後（`/usr/local/bin/ollama`），跳過 install.sh，**手動寫 `/etc/systemd/system/ollama.service`** 並 `useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama` 建好專用使用者再 enable
2. **`sudo apt upgrade` 會跑 initramfs 重建**，第一次裝完跑大約 5 分鐘，期間別中斷
3. **Imager 預設 user 預設 NOPASSWD sudo** — 自動化指令可直接 `sudo -n` 不用密碼

## 重要安全紀律

- 本檔**只記設定路徑與配置**，**不含**密碼 / SSH 私鑰 / Cloudflare credentials
- 在 Pi5 上：
  - `~/.cloudflared/cert.pem` 跟 `<tunnel-uuid>.json`（**chmod 600**，不要備份到雲）
  - 一般使用者密碼僅在本機 sudoers / Imager 設定紀錄
- 對外曝光 Ollama API 前先確認 LAN 是 trusted 或加 VPN

## 開機自動啟動驗證

```
systemctl is-enabled ollama cloudflared docker
# 預期：三個都 enabled
```

## 後續里程碑

- **M2 LLM Router**：抽 `core/llm_router.py`，OpenAI + Ollama 兩家先接；接 Pi5 Ollama 走 Tailscale（避開 Cloudflare 100s HTTP 限制）
- **M3 LINE Bot Adapter**
- **M4 第一條被動推播 graph**（Pi5 cron + RabbitMQ → LINE push）

詳見 [roadmap #8](https://github.com/towNingtek/ai-eva/issues/8)。
