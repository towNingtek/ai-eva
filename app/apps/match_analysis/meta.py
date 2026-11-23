# match_analysis app —— 媒合分析 MVP（ai-eva EPIC #176 / #184）。
# A 從自己可管理的專案選一案，再指定 2–4 個對象；照媒合標準（standard_yunlin_v1.yaml）
# 判 B1–B8 與 Need／Offer、算關係與狀態，回覆分事實／推論／建議，資料不足時主動追問一題。
# 與過渡版 project_match 並存（townway#63 上線後舊版才退場），由站台工具設定（enabled_apps）決定開哪個。
META = {
    "id": "match_analysis",
    "project": "sechome",
    "label": "媒合分析",
    "icon": "🧭",
    "cl_icon": "Compass",
    "is_default": False,
    "show_in_menu": True,
    "description": "選我的專案 A，再指定 2–4 個對象：依媒合標準判 B1–B8 與 Need／Offer，"
                   "列互補候選／共同尋找第三方／可聯合或交流（附兩邊原文），事實／推論／建議分開標示；"
                   "資料不足時主動追問。第一期不推薦、不自動聯絡。",
    "inputs": [],
    "outputs": ["match_analysis"],
}
