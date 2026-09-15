# chart_analysis app — (b) 卡首例落地：薄 app 串 sustainability/chart module，
# 資料後端依登入者給 CMSDataSource（SSO）或 StubDataSource（無 SSO 時的回退）。
# 支援 (a) 卡：它屬於 sechome，可被 project-level enabled_apps 遮蔽
# （法規檢核屬 yunlin，sechome 只掛 chart 查詢，不掛法規功能）。
META = {
    "id": "chart_analysis",
    "project": "sechome",
    "label": "圖表查詢",
    "icon": "📊",
    "cl_icon": "BarChart3",
    "is_default": False,
    "show_in_menu": True,
    "description": "專案圖表查詢（年度/地區/SDG 過濾）——資料後端可切換（CMS / stub）。",
    "inputs": ["year", "district", "sdgs"],
    "outputs": ["chart_query_result"],
    "ai": False,
}