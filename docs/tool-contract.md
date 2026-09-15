# Tool Contract（#84 / #128）

> 定義「產品資料後端」與 app/module 之間的介面。所有資料後端（CMS、stub、未來的 DB/第三方）
> 都透過 `app/adapters/` 暴露，consumers（chainlit app、copilot、module handler）
> **只依賴這個契約，不直接碰 `ToolRuntime`**。

## 一、QuerySpec — 一次呼叫的請求

`app/adapters/base.py::QuerySpec`

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `tool` | `str` | ✅ | CMS/tool 名稱，例 `dashboard_chart_query`、`save_sdg` |
| `args` | `dict` | 預設 `{}` | tool 參數 |
| `confirmed` | `bool` | 預設 `False` | 需要使用者確認（needs_confirm）時由呼叫端送出 |
| `timeout` | `float\|None` | 預設 `None` | 覆寫預設 timeout（秒） |
| `encoding` | `str\|None` | 預設 `None` | `json`＝JSON body；`None`＝form |
| `conversation_id` / `node_id` | `str\|None` | - | 選填：情境識別（未來用途） |

`QuerySpec` 也可從 dict 建立（`QuerySpec(**data)`）。(註：`DataSource` 介面不含 `spec()`，
那是 ToolRuntime 層的 helper；adapter 只吃 `QuerySpec` 進 `query()`。)

## 二、AdapterResult — 一次呼叫的回傳

`app/adapters/base.py::AdapterResult`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `status` | `str` | **`ok` / `need_confirm` / `denied` / `error`**（四態，唯一正規化來源） |
| `provider` | `str` | 資料後端 id（`tplanet-cms`、`stub`、…） |
| `data` | `Any` | 成功時的資料（CMS 已被 `unwrap_cms` 解出；stub 直接給回） |
| `raw` | `Any` | 原始回傳（除錯用） |
| `reason` | `str` | 非 ok 時的人話錯誤訊息 |
| `tool` | `str` | 對應的 tool 名 |

### 狀態語意
- `ok`：資料拿到。`data` 內含 business 資料。
- `need_confirm`：工具要使用者確認。`data` 可含 `{title, description, confirm_text, args}`。
- `denied`：權限/manifest 不允許。`reason` 說明。
- `error`：執行錯誤（tool 不存在、500、timeout 等）。`reason` 說明。

### CMS 特定
`CMSDataSource` 把 `ToolRuntime` 的 `{status, result, reason, tool}` 正規化：
`success/manifest 允許 → ok`；`needs_confirm → need_confirm`；`denied → denied`；
其餘 → `error`。`result.data` 會被 `unwrap_cms` 解包（沒有 `data` key 就原樣）。

## 三、status 依賴規則（module / caller 通用）
1. 先檢查 `status == "ok"` 才碰 `data`。
2. 遇到 `need_confirm` → 把 `data.args` 存起來問使用者；使用者確認後用
   `QuerySpec(confirmed=True)` 重送。
3. 遇到 `denied` / `error` → 回給使用者「做不了 + 原因」，**不要**假設一定能重試。
4. 不要用 `raw` 判斷成敗——一律看正規化的 `status`。

## 四、註冊與取得
- `app/adapters/registry.py::REGISTRY`：`provider` → adapter class。
  內建 `tplanet-cms`、`stub`。
- `create(provider, **kwargs)` 建實例；`get_adapter_cls(provider)` 拿 class。
- 新後端：繼承 `DataSource`（async `query(spec) -> AdapterResult`），
  註冊進 `REGISTRY` 即可，**consumers 零改動**（#128 判準 2「換後端不改邏輯」）。