# project_match app —— 專案媒合 1.5 手動選擇版（townway#66/#71；前身 ai-eva#134 過渡版）。
# 定位：sechome cutover 期間維持舊版（tplanet stable PlanningModule）的媒合可用性，
# townway#63 正式媒合系統上線後整包退場。刻意不做候選排序 / SDG 比對 / 結構化媒合模型。
# project=sechome：舊版就掛在 sechome 站台，且退場時只要刪這個目錄，不影響 core/yunlin。
META = {
    "id": "project_match",
    "project": "sechome",
    "label": "專案媒合",
    "icon": "🤝",
    "cl_icon": "Handshake",
    "is_default": False,
    "show_in_menu": True,
    "description": "手動選擇媒合對象（可多選，一次載入 20 筆）：我的專案 × 每個對象各出一份互補性分析與合作提案（1.5 版）。",
    "inputs": [],
    "outputs": ["match_proposal"],
}
