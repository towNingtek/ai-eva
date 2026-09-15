# sustainability — SDG / SROI 模組（#84 Product Modules / #129 搬遷）。
# SDG 與 SROI 各自獨立 module（sustainability.sdg、sustainability.sroi），
# 共用同一張 meta （行動式：SDG generate / SROI estimate）。
META = {
    "id": "sustainability.sdg",
    "label": "SDG 自動產生",
    "project": "sechome",
    "description": "讀專案資訊 → LLM 產 SDG 對應 → 存回（資料後端經 adapter）。",
    "actions": ["generate"],
}