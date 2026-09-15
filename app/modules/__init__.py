"""Product Module 套件（#84 / #129）。

module = 可組合、可替換資料後端的 AI 工作單元。與 app 的差別：
- app 是「前端工具」：有 Chainlit UI（cl.Message），靠 handler(payload, msg)。
- module 是「後端單元」：不碰 UI，只吃 `DataSource`（adapter）＋ context，
  純邏輯、可單元測試、可被多個 app / surface 呼叫。

每個 module 目錄結構（沿用 app 慣例）：
  meta.py     META dict：{id, label, project, description, actions?}
  handler.py  async handle(ctx, action, payload) -> dict

`ctx` 是 ModuleContext（見 base.py），承載 project / adapter / llm 等執行環境。
module 內不得直接 import CMS、不寫死 uuid/後端欄位 —— 一律走 ctx 注入。
"""