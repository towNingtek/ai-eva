# 法規檢核準確率評估（tplanet-multi-tenant#113）

- `plans10.json`：雲林正式站 10 案計畫理念（`yunlin.4impact.cc/api/projects/info/<id>`，2026-11-17 取），清理方式同 regulation_check app。
- `golden_draft.py` → `golden.json`：**golden 草案 v0.3**，**不看系統輸出**，用 R0–R11 規則＋計畫書原文片段決定每案應觸發哪些法（每條附依據）。待甲方書面確認（5 個工作天，逾期視同同意）。
- `score.py`：Recall／Precision（法規層級、10 案合併；鄰條／同風險不同條算正確；範圍外不計；甲方 `accept_system` 不扣分）。
- `run.py`：對 10 案跑正式 judge（`python -m app.regulations.eval.run <out_dir>`，一輪約 11 分鐘、約 US$20）。

## 結果
| 輪 | judge | golden | Recall | Precision |
|---|---|---|---|---|
| 1 | beta d0b7469（標準 v0.2） | v0.1 | 100% | 39.5% |
| 1 | 同上 | v0.3 | 97.8% | 69.5% |
| **2** | **本分支（標準 v0.3.1，+4 個適用前提閘門）** | **v0.3** | **97.8%** | **81.0%** ✅ |

第 2 輪原始輸出與分數在 `runs/2026-11-17-r2/`。
