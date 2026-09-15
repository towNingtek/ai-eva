# Module Contract（#84 / #129）

> 產品的「領域能力」以 module 為單位（SDG、SROI、chart、project-management…）。
> Module 就是「一份 meta + 一個 receive(ModuleContext, payload)」，**不直接碰
> ToolRuntime / adapter / DB**——資料一律透過 `ctx.data.query(QuerySpec)` 走 adapter。

## 一、Module 結構

一個 module 是一個目錄，自動發現（`app/modules/*/` 各一層、扁平掃描）：

```
app/modules/<package>/
├── __init__.py
├── meta.py        # META = { id, label, project, description, actions }
└── handler.py     # async handle(ctx: ModuleContext, payload: dict) -> dict
```

`id` 慣例 `<project>.<name>`（例 `sechome.chart`）。`project` 是**擁有此 module 的
site 概念**（現階段 site≡project，見 #84 論述），不是資料後端。

## 二、ModuleContext（app/modules/base.py）

Module handler 唯一的外界窗口：

| 欄位 | 必填 | 說明 |
|---|---|---|
| `project` | ✅ | 呼叫來源 project（決定啟用矩陣） |
| `data` | ✅ | `DataSource` 實例（CMS/stub/…）——**module 只認這個** |
| `action` | 選用 | 要執行的動作（對應 META.actions） |
| `make_llm` / `api_key` / `llm_user` | 選用 | LLM 需要時由呼叫端提供 |
| `meta` | 選用 | 額外中繼資料 dict（如 `site`） |

`ctx.result(ok, reply, **data)` 產制式回傳：**`{ok, reply, data, error}`**。
- `ok=True` → caller 顯示 `reply`（內部可含 `data`）
- `ok=False` → `reply` 是不成的人話，`error` 保留技術訊息

Module **不自己決定要回什麼設備/UI** —— caller（chainlit app、copilot）負責。

## 三、註冊與執行（app/modules/registry.py）

- `discover()`：掃 `app/modules/**` 找 `meta.py`，回 `{id: Module}`。
- `get_by_id(id)`：查模組。
- `modules_for_project(project, enabled=None)`：啟用矩陣過濾後的模組（
  `enabled=None`=全開，向後相容；`core` 常駐不受矩陣影響）。
- `invoke(module_id, ctx, payload)`：`get_by_id` → `handle(ctx, payload)`。
  module 找不到/action 不存在 → `{ok: False, reply: 人話}`。

啟用矩陣存在 `projects.metadata.enabled_modules`（DB helper：`get/set_enabled_modules`，
模式同 apps 的 `enabled_apps`）。

## 四、Module 寫法守則（對應 #84 phase 3、#129 判準）
1. **資料不落地**：所有讀寫走 `ctx.data.query(QuerySpec(...))`，不要 `import` ToolRuntime。
2. **LLM 走 ctx**：要用 AI 就跟呼叫端拿 `make_llm`；不要在 module 內自行建立 API key 來源。
3. **uuid 由 caller 注入** payload，module 不從全域/環境變數抓（#129 已修掉寫死 uuid）。
4. **回傳一律 `ctx.result()` 制式**，不 raise；connect/HTTP 錯誤由 adapter 轉 `status=error`。
5. **`needs_confirm` 的寫入動作**：module 回 `need_confirm` 的結果（傳回 adapter 的
   `data`），由 caller 問使用者、再以 `confirmed=True` 重送——module 不自己出 UI。

## 五、資料後端切換（#128 / #129 判準 2）
同一 module 換後端 = 換 `ctx.data`（`CMSDataSource(runtime)` → `StubDataSource(data)`），
**module 自身零修改**。測試即以「同一 module 分別接 CMS 與 stub，回傳結構一致」驗證
此能力（見 `tests/test_modules.py`）。