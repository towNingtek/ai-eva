# 法規檢核星圖正式化（#180 定案）

2026-11-19 yillkid 在雲林測試站驗收通過。本文件記錄實際採用的做法。

## 合併方式

- **入口不變**：AI 秘書工具區點「⚖ 法規檢核」才開啟星球工作區；其他工具（含專案媒合）不受影響。
- **功能旗標**：`TANGLE_LAW_TASK=1` 才啟用，預設關閉；未啟用時維持原本的聊天流程。目前只在雲林測試站（GitOps `k8s/apps/ai-eva`）開啟，正式站未啟用。
- **同一對話、同一任務**：任務存在 `app/apps/regulation_check/task.py`，依 CMS 身分（issuer、project、tenant、user、email）＋ thread 隔離。返回聊天不取消；再次點選工具接回原任務、不重跑；只有「開始新的法規檢核」才建立新任務。重新整理或從歷史紀錄開啟時，經輸入框旁「⋯ → 法規檢核」接回。
- **報告**：仍是原對話的 `.md` 附件，內容由原報告產生器（`app/regulations/report.py`）產出。
- 相關 PR：#195（整合）、#196（耗時顯示整數秒）、#197（完成後套原畫法、點衛星說明）。

## 資料對應

試作站的示範資料（`public/tangle/kv-law-mock.js` 的 `KV_LAW.projects[...].law`）與真實判定結果用同一個形狀，由 `handler.domain_view()` 從判定結果產生，前端畫法共用、不另寫一套：

| 欄位 | 來源（真實判定結果） |
|---|---|
| `state: hit` | 該法領域有 ≥1 條判定「觸發」 |
| `state: gap`、`missing` | 該法領域適用前提「待確認」或有「需補資訊」；`missing` 取標準 `clarify_questions` 該法領域第一題的欄位名，否則取前提的缺少說明 |
| `state: na` | 其餘（不觸及、前提不成立） |
| `confidence` | 觸發條文中最高的把握程度（high／mid／low） |
| `count.risk`／`count.note` | 觸發條文依報告區塊（違規風險／合規提醒）去重計數 |
| `evidence` | 觸發條文中**已驗證**為計畫書原文的引用（最多 3 段，各 40 字） |
| `clauses` | 觸發條文（法規、條次、類型、情境、risk／note），違規風險優先，最多 12 條 |
| `hit`／`total` | 觸發條數／該法領域逐條判定條數 |

執行中只有各法領域進度（`progress`），畫簡化衛星（命中／檢核數）；完成後改用上表資料，套回原有畫法（光暈、證據點、光流、缺資料霧、走進衛星的條文碎片）。點完成後的衛星送出 `domain` 事件，Eva 在對話說明該法領域，**不重判**。

## 檢查

| 檢查 | 指令 | 驗什麼 |
|---|---|---|
| 任務生命週期 | `python -m pytest -q tests/test_regulation_task.py` | 同一任務重入、只判定一次、原附件、權限撤回 |
| 星圖資料 | `python -m pytest -q tests/test_regulation_domain_view.py` | 以真實大庄結果產生 10 法領域、點衛星不重判 |
| 瀏覽器合約 | `node tests/lab/law-task.check.js` | 選案、進度、耗時整數、更新不重開、回聊天下載 |
| 真實結果特效 | `node tests/lab/law-live-effects.check.js` | 光暈、霧、證據點、光流移動、條文碎片、點衛星事件 |
| 原有動畫 | `node tests/lab/animation-keep.check.js` | 16 項動畫保留（`ALL KEPT 16`） |
| 實站 | Playwright 於雲林測試站（`sha-409cd54`／`sha-1813bec`） | 原入口、同一任務重入、只提交一次、重載後接回、下載原報告 |

準確率不受 UI 影響：判定程式（`app/regulations/`）換 UI 前後無差異；星球版測試站以正式站 10 案重跑 Recall 97.0%、Precision 82.4%（#190）。
