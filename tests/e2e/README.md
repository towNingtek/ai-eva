# AI-Eva E2E（#111 法規檢核 / #112 知識庫管理）

用 Playwright 實跑一次驗收 KPI 並斷言，對應 GitHub issue
[town-intelligent/tplanet-multi-tenant#111](https://github.com/town-intelligent/tplanet-multi-tenant/issues/111)、
[#112](https://github.com/town-intelligent/tplanet-multi-tenant/issues/112)。

## 前置

1. **一個掛載目前程式碼的 ai-eva 實例**（跑著的 beta 容器是舊 image，測不到新程式）：

   ```bash
   cd <repo>
   docker run -d --name eva-e2e \
     --network ai-eva-beta_default --add-host host.docker.internal:host-gateway \
     -v "$PWD:/app" -w /app --env-file .env \
     -e LITELLM_API_BASE=http://host.docker.internal:4000/v1 \
     -e LITELLM_API_KEY="$(grep '^LITELLM_MASTER_KEY' .env | cut -d= -f2-)" \
     -p 7871:7871 ai-eva \
     chainlit run app/main.py --host 0.0.0.0 --port 7871 --headless
   ```

   beta 的 `.env` 直接打 OpenAI（`LITELLM_API_BASE=https://api.openai.com/v1`），
   所以要覆蓋成 LiteLLM proxy，判定才用得到 `openai-5.4-xiaozhen`。

2. **dev CMS 容器跑著**（`mt-dev-backend`）—— 用來簽 SSO handoff token。

3. `npm install && npx playwright install chromium`

## 跑

```bash
npx playwright test              # 全部
npx playwright test -g 可上傳     # 單一 KPI
npx playwright show-report       # 失敗時看 trace
```

## 登入怎麼過

法規檢核要讀 CMS 專案，得是「從 CMS 進來」的 SSO 登入態。`global-setup.js` 每次跑之前
用 `mint-token.sh` 簽一張 RS256 handoff token（TTL 10 分鐘），測試再走
`/sso/handoff?token=…` 進站 —— 等同使用者在 CMS 按「進 AI Eva」。

`CMS_TENANT` 預設 `dev`：填 `yunlin` 會讓 ai-eva 去 `yunlin-beta.4impact.cc` 拿 manifest，
而 token 是 dev 那台簽的 → 401。

## 涵蓋的 KPI

| Issue | KPI | 測試 |
|---|---|---|
| #111 | 接收計畫書 → 檢核 → 產含 5 區塊 .md 報告 | `regulation-check.spec.js` |
| #111 | 涵蓋 10 法領域；範圍外標「需補語料/未評估」 | 同上（斷言報告內文） |
| #111 | 可下載 .md 報告 | 同上（攔 download 事件並讀檔） |
| #112 | 法規 PDF 可上傳 | `knowledge-base.spec.js` |
| #112 | 可重複使用已建立之法規索引 | 同上 |
| #112 | 檢核時可引用已上傳法規資料 | 兩支合看：語料庫清單 + 報告逐條判定總表引用法規 |

## 已知的手工步驟

- 測試資料是 R0 盲生的「晴耕社區」計畫書（uuid `90948229`，在 dev CMS）。換環境要改
  `regulation-check.spec.js` 的 `PLAN` 常數。
- 上傳測試會在 DB 留下一筆 `pending` 法規（刻意的：證明上傳不會進判定分母）。
  要清掉：`DELETE FROM regulations WHERE origin='upload';`
