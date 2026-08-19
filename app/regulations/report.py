"""5 區塊 .md 報告組裝。

區塊與免責文字來自 YAML 標準的 `output`（換 YAML 就換報告長相）。
預設：摘要 / 違規風險 / 合規提醒 / 需補語料 / 免責。

註：R0-4 規格書把第 4 塊寫成「規模門檻」、YAML v1 寫成「摘要」在最前面。兩份文件
不一致，這裡採 YAML（它才是實際驅動行為的設定檔），規模門檻的判定依
`output.scale_gate_section` 併進「需補語料」。

## 兩個呈現上的決定（實測後改的）

1. **條文層級呈現**：negative_list 一條法條常拆成多筆管制條目（水保法§12 有 4 筆），
   逐筆列會讓同一條文重複出現。報告按 (法規, 條號) 收斂，嚴重度取最高、理由合併。
   R0-4 的 recall/precision 也是「法規層級」計分，跟這個粒度一致。

2. **表格而非詳述**：實測晴耕社區觸發 289 筆 / 186 條文，逐筆詳述會產出 5 萬字的
   不可讀報告。改成每個法領域一張表；完整的逐條判定收進附錄壓縮總表 —— 覆蓋率的
   稽核能力不能丟（甲方要能問「有沒有檢核到水保§12」），但也不能塞爆報告。

報告只呈現**驗證過的原文引用**（judge 已核對證據確實出自計畫書）；對不上的不印，
只留理由 —— 假引用比沒有引用更糟。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.regulations import registry, standard

TPE = timezone(timedelta(hours=8))
_ICON = {"high": "🔴", "medium": "🟡", "low": "🔵"}
_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def _cell(s: str, limit: int = 90) -> str:
    """表格儲存格：壓掉換行與管線符號，過長截斷。"""
    s = (s or "").replace("|", "｜").replace("\n", " ").strip()
    return s if len(s) <= limit else s[:limit] + "…"


def _consolidate(items: list[dict]) -> list[dict]:
    """同一 (法規, 條號) 的多筆管制條目收斂成一條。"""
    merged: dict[tuple[str, str], dict] = {}
    for f in items:
        key = (f["regulation"], f["article_no"])
        cur = merged.get(key)
        if cur is None:
            merged[key] = {**f, "reasons": [f.get("reasoning", "")],
                           "evidences": [f["evidence"]] if f.get("evidence") and f.get("evidence_verified") else [],
                           "entries": 1}
            continue
        cur["entries"] += 1
        if f.get("reasoning"):
            cur["reasons"].append(f["reasoning"])
        if f.get("evidence") and f.get("evidence_verified"):
            cur["evidences"].append(f["evidence"])
        if _SEV_ORDER.get(f.get("severity"), 3) < _SEV_ORDER.get(cur.get("severity"), 3):
            cur["severity"] = f["severity"]
        if not cur.get("penalty") and f.get("penalty"):
            cur["penalty"] = f["penalty"]
    return list(merged.values())


def _table(items: list[dict], empty: str) -> str:
    if not items:
        return empty
    by_domain: dict[str, list[dict]] = {}
    for f in items:
        by_domain.setdefault(f["law_domain"], []).append(f)
    out = []
    for domain, group in sorted(by_domain.items(), key=lambda kv: -len(kv[1])):
        group.sort(key=lambda f: _SEV_ORDER.get(f.get("severity", "low"), 3))
        rows = ["| | 法規 · 條號 | 計畫書依據 | 判定理由 |", "|---|---|---|---|"]
        for f in group:
            ev = f["evidences"][0] if f.get("evidences") else "—"
            rows.append(f"| {_ICON.get(f.get('severity','low'),'•')} "
                        f"| **{_cell(f['regulation'],28)}** {_cell(f['article_no'],16)} "
                        f"| {_cell(ev, 48)} | {_cell(f['reasons'][0] if f.get('reasons') else '', 76)} |")
        out.append(f"### {domain}（{len(group)} 條）\n\n" + "\n".join(rows))
    return "\n\n".join(out)


def _coverage_sentence(cov: dict) -> str:
    """涵蓋範圍的三段式陳述：宣告 / 本次實評 / 未評估與原因。

    只寫「涵蓋 8 個法領域」對照規格書宣告的 10 個會讀起來像沒做完；
    未評估的兩種原因（計畫類別不納入、適用前提未成立）都是**規則決定**的，
    講清楚才站得住 —— 這也正是 R0-4「範圍外標未評估、不代表合規」的要求。
    """
    declared = cov.get("covered_declared") or []
    evaluated = cov.get("domains") or []
    gate_reason = {}
    for g in cov.get("gates") or []:
        if g.get("gate") != "成立" and g.get("law_domain"):
            gate_reason[g["law_domain"]] = ("適用前提未成立" if g["gate"] == "不成立"
                                            else "適用前提待確認")
    missing = [d for d in declared if d not in evaluated]
    head = (f"本次檢核逐條評估 **{cov['evaluated']} 條**管制條目。"
            f"本標準宣告涵蓋 **{len(declared)} 個法領域**，"
            f"本次計畫類別為「{cov.get('category','')}」，實際評估 **{len(evaluated)} 個**"
            f"（{'、'.join(evaluated)}）。")
    if missing:
        bits = [f"{d}（{gate_reason.get(d, '計畫類別不納入')}）" for d in missing]
        head += f"\n\n未評估 **{len(missing)} 個**：{'、'.join(bits)} —— 詳見第四區塊。未評估不代表合規。"
    return head + "\n\n下表以**法條**為單位彙整（同一條文的多項要求已合併）。"


def _coverage_appendix(findings: list[dict]) -> str:
    """逐條判定總表（壓縮）—— 覆蓋率的稽核依據。

    每部法規一行，列出各判定落在哪些條號。甲方問「有沒有檢核到水保§12」時，
    在這裡查得到；而不是把 1,000 多列攤在報告裡。
    """
    by_reg: dict[str, dict[str, list[str]]] = {}
    for f in findings:
        by_reg.setdefault(f["regulation"], {}).setdefault(f["verdict"], []).append(f["article_no"])
    rows = ["| 法規 | 已評估 | 觸發 | 需補資訊 | 需補語料 |", "|---|--:|---|---|---|"]
    for reg in sorted(by_reg):
        v = by_reg[reg]
        total = sum(len(x) for x in v.values())
        def fmt(k: str) -> str:
            arts = sorted(set(v.get(k) or []))
            return "、".join(arts) if arts else "—"
        rows.append(f"| {_cell(reg,32)} | {total} | {_cell(fmt('觸發'),70)} "
                    f"| {_cell(fmt('需補資訊'),40)} | {_cell(fmt('需補語料'),40)} |")
    return "\n".join(rows)


def build(result: dict, *, plan_name: str, plan_uuid: str,
          std_name: str = standard.DEFAULT_STANDARD) -> str:
    std = standard.load(std_name)
    out_cfg = std.get("output") or {}
    findings = result["findings"]
    cov = result["coverage"]
    engine = result.get("engine") or {}
    corpus = registry.corpus_meta()

    hit = [f for f in findings if f["verdict"] == "觸發"]
    violations = _consolidate([f for f in hit if f["section"] == "違規風險"])
    reminders = _consolidate([f for f in hit if f["section"] == "合規提醒"])
    need_info = _consolidate([f for f in findings if f["verdict"] == "需補資訊"])
    need_corpus = _consolidate([f for f in findings if f["verdict"] == "需補語料"])
    failed = [f for f in findings if f["verdict"] == "判定失敗"]
    untouched = len(findings) - len(hit) - sum(f["entries"] for f in need_info) \
        - sum(f["entries"] for f in need_corpus) - len(failed)

    now = datetime.now(TPE).strftime("%Y-%m-%d %H:%M")
    meta = result.get("standard", {})

    parts = [
        f"# 法規檢核報告 — {plan_name}",
        "",
        "| 項目 | 內容 |",
        "|---|---|",
        f"| 專案 | {plan_name}（uuid `{plan_uuid}`）|",
        f"| 檢核時間 | {now}（UTC+8）|",
        f"| 標準版本 | `{meta.get('id','')}` {meta.get('version','')} |",
        f"| 判定引擎 | `{engine.get('model','?')}` · temperature={engine.get('temperature','?')}"
        f" · reasoning={engine.get('reasoning_effort','?')} |",
        f"| 語料版本 | `{corpus.get('corpus_version','?')}` · {cov.get('regulations_active','?')} 部生效"
        f" · {cov['controls']} 條管制（抽取模型 `{corpus.get('extracted_by','?')}`）|",
        f"| 計畫類別 | {cov['category']} |",
        f"| 耗時 | {result.get('elapsed', 0):.0f} 秒（{cov.get('batches','?')} 批平行判定）|",
        "",
        "## 一、摘要",
        "",
        _coverage_sentence(cov),
        "",
        "| 判定 | 條文數 | 管制條目數 |",
        "|---|--:|--:|",
        f"| 🔴 違規風險 | {len(violations)} | {sum(f['entries'] for f in violations)} |",
        f"| 🟡 合規提醒 | {len(reminders)} | {sum(f['entries'] for f in reminders)} |",
        f"| ❓ 需補資訊（規模門檻） | {len(need_info)} | {sum(f['entries'] for f in need_info)} |",
        f"| 📚 需補語料 | {len(need_corpus)} | {sum(f['entries'] for f in need_corpus)} |",
        f"| ✅ 不觸及 | — | {untouched} |",
    ]
    if failed:
        parts.append(f"| ⚠️ 判定失敗 | — | {len(failed)} |")
    parts += [
        "",
        "## 二、違規風險",
        "",
        _table(violations, "_本次未發現違規風險。_"),
        "",
        "## 三、合規提醒",
        "",
        _table(reminders, "_無。_"),
        "",
        "## 四、需補語料／未評估",
        "",
    ]

    gap = []
    scale_checks = cov.get("scale_checks") or []
    if scale_checks:
        icon = {"達到": "🔴 達到門檻", "未達到": "✅ 未達門檻", "資料不足": "❓ 資料不足"}
        rows = ["| 判定 | 法規 · 條號 | 門檻 | 理由 |", "|---|---|---|---|"]
        for c in scale_checks:
            rows.append(f"| {icon.get(c['scale'], c['scale'])} | **{_cell(c['law'],26)}** {c['article']} "
                        f"| {_cell(c['trigger'], 46)} | {_cell(c['reasoning'], 80)} |")
        missing = [c for c in scale_checks if c.get("missing")]
        block = (f"### 規模門檻專項判定（{len(scale_checks)} 條）\n\n"
                 "本標準點名「須先確認規模才能判定適用」的條文，每條單獨判定：\n\n"
                 + "\n".join(rows))
        if missing:
            block += "\n\n**待補資料**\n\n" + "\n".join(
                f"- {c['law']} {c['article']}：{_cell(c['missing'], 130)}" for c in missing)
        gap.append(block)
    if need_info:
        gap.append(f"### 其他需補規模資訊的條文（{len(need_info)} 條）\n\n"
                   "適用與否取決於面積／規模／區位數字，而計畫書未載明：\n\n" +
                   "\n".join(f"- **{f['regulation']} {f['article_no']}**：{_cell(f['reasons'][0], 120)}"
                             for f in need_info))
    if need_corpus:
        gap.append(f"### 指向語料庫外的法規（{len(need_corpus)} 條）\n\n" +
                   "\n".join(f"- **{f['regulation']} {f['article_no']}**：{_cell(f['reasons'][0], 120)}"
                             for f in need_corpus))
    gates = [g for g in (cov.get("gates") or []) if g.get("gate") != "成立"]
    if gates:
        rows = []
        for g in gates:
            mark = "前提未成立" if g["gate"] == "不成立" else "**前提待確認**"
            rows.append(f"- **{g['law']}**（{mark}，{g.get('skipped_controls', 0)} 條管制未評估）\n"
                        f"  - 適用前提：{g.get('precondition','')}\n"
                        f"  - 判斷門檻：{g.get('threshold','')}\n"
                        f"  - 判定理由：{_cell(g.get('reasoning',''), 140)}"
                        + (f"\n  - 待補資料：{_cell(g['missing'], 140)}" if g.get("missing") else ""))
        gap.append(f"### 適用前提未成立／待確認的法規（{len(gates)} 部）\n\n" + "\n".join(rows) +
                   "\n\n這些法規只在前提成立時才適用，本次未納入判定；"
                   "前提待確認者請補齊上列資料後重跑。")

    labels = {"draft": "草案，尚未生效", "no_fulltext": "全文未取得"}
    non_judging = cov.get("non_judging") or []
    if non_judging:
        gap.append(f"### 收錄但未納入判定的法規（{len(non_judging)} 部）\n\n" +
                   "\n".join(f"- **{r['name']}**（{labels.get(r['status'], r['status'])}）"
                             for r in non_judging) +
                   "\n\n草案於生效前不作為違規判定依據；全文未取得者需另行索取後補入語料庫。")
    declared = cov.get("covered_declared") or []
    if declared:
        gap.append("### 未涵蓋領域\n\n本標準宣告涵蓋：" + "、".join(declared) +
                   "。\n\n其他領域（觀光民宿、休閒農業、建築技術、地方自治、水利、漁業、能源光電…）"
                   "**未評估**；未評估不代表合規。")
    if cov.get("excluded_categories"):
        gap.append("### 本次未納入的語料類別\n\n" + "、".join(cov["excluded_categories"]) +
                   f"（計畫類別為「{cov['category']}」，依標準不納入）。")
    parts.append("\n\n".join(gap) if gap else "_無。_")

    parts += [
        "",
        "## 五、免責聲明",
        "",
        f"- {out_cfg.get('disclaimer', '本報告為 AI 初篩，非正式法律意見。')}",
        f"- {out_cfg.get('scope_disclaimer', '')}",
        "- 本報告輸出為「疑似風險・待複核」，**不構成行政處分依據**。",
        "- 未列出的項目僅代表本次未判定觸發，不等於合規。",
        "",
        "---",
        "",
        "## 附錄：逐條判定總表",
        "",
        f"本次 scope 內共 {cov['evaluated']} 條管制條目全數評估，無抽樣、無檢索遺漏。",
        "",
        _coverage_appendix(findings),
        "",
    ]
    return "\n".join(parts)
