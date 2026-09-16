# project_match app —— 過渡版專案媒合（ai-eva#134）。
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
    "description": "從可管理的專案中隨機挑兩個，做互補性分析並提出合作提案（過渡版，townway#63 上線後退場）。",
    "inputs": [],
    "outputs": ["match_proposal"],
}
