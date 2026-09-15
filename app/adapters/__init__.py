"""Adapter 套件 — 把「資料後端」與「功能邏輯」切開（#128）。

core 決策：module 只認 `DataSource.query()` 的標準介面，不知道資料後端是
CMS、Google Sheet、IoT 還是 stub。切換後端 = 換一個 adapter，module 本體零修改。

- base.py     AdapterResult / QuerySpec / DataSource（介面契約）
- cms.py      tplanet-cms adapter（包既有 ToolRuntime，含 deny-by-default / needs_confirm / encoding）
- stub.py     測試/示範用的假資料 adapter（證明同一 module 換後端輸出一致）
- registry.py adapter 註冊與取名（provider → 實作）
"""