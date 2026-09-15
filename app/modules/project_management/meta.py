# sechome.project-management — 專案管理模組（#84 / #129 搬遷）。
# 原 copilot 內建引導式建案流程的 module 化：guidance（LLM prompt）
# 收在 module 內，資料後端（create_project / list_my_projects）走 adapter。
META = {
    "id": "sechome.project-management",
    "label": "專案管理",
    "project": "sechome",
    "description": "專案建立（引導式問答）與列專案；資料後端經 adapter。",
    "actions": ["list_projects", "create_project"],
}