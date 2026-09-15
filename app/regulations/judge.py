"""判定引擎 —— 計畫書 × 管制條目，按法領域平行跑。

## 形狀（為什麼是這樣切）

    計畫書  →  整份不切，每個呼叫都拿到完整的
    管制條目 →  逐條，按 law_domain 分組，組內再分批

計畫書不切是關鍵：違規常要跨章節才成立（第三章說「休耕農地開挖滯洪池」、
第四章說「0.5 公頃」，合起來才觸發農地變更門檻）。切了就永遠判不出來，
而計畫書本身才幾百到幾千字，塞進去成本可以忽略。

## 為什麼每一條都要判（含「不觸及」）

覆蓋率是驗收 KPI。judge 對 scope 內的**每一條**都回判定，所以報告能誠實寫
「本次檢核涵蓋 N 條、M 個法領域」，甲方問「有沒有檢核到水保法§12」時查得出
逐條理由。這是 similarity 檢索給不出來的東西。

判定內容本身不是位元級可重現（LLM），但**覆蓋率是**：同一份計畫、同一版語料，
N 和 M 永遠一樣。#111 驗收的是流程與覆蓋，判定準確率是 #113。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Awaitable, Callable, Optional

from app.core.llm import make_llm
from app.regulations import registry, standard

logger = logging.getLogger(__name__)

# 單次呼叫最多帶幾條管制條目。太多會拖長輸出、增加漏判；太少則呼叫次數爆掉。
BATCH_SIZE = 40
# 同時在跑的呼叫數。上游是 LiteLLM proxy，開太大只會排隊 + 撞 rate limit。
CONCURRENCY = 8
CALL_TIMEOUT = 300.0

ProgressCb = Optional[Callable[[dict], Awaitable[None]]]

VERDICTS = ("觸發", "不觸及", "需補資訊", "需補語料")


def _normalize_verdict(raw: str, evidence: str) -> tuple[str, bool]:
    """模型偶爾自創判定值（實測出現過「低觸發」）。強制收斂回 enum。

    回 (verdict, 是否原本就合法)。收斂規則保守偏 recall：像觸發的就當觸發、
    有引用的就當觸發，其餘歸不觸及 —— 判定值怪異本身就代表模型沒把握，
    後續 confidence 會被降級，由偽陽性政策決定它進哪一區。
    """
    v = (raw or "").strip()
    if v in VERDICTS:
        return v, True
    for known in VERDICTS:
        if known in v:              # 「低觸發」「疑似觸發」→ 觸發
            return known, False
    return ("觸發" if evidence.strip() else "不觸及"), False

_SYSTEM = """你是協助審查農村再生計畫書的法規檢核助理。

你會拿到一份社區計畫書，以及一組「管制條目」（每條是某部法規的一項要求）。
請對**每一條**管制條目判斷這份計畫有沒有觸發它，一條都不能略過。

## 判定取向（重要，跟一般法律意見不同）

這份報告的用途是**初篩後交人工複核**，驗收標準明訂「重 recall、輕 precision」：
漏抓等於給了假合格，誤報則由複核者濾掉。所以**有疑慮就標出來**，用 confidence
表達你的把握程度，不要因為不確定就判「不觸及」。

特別是**法定區位/編定**（山坡地、特定水土保持區、使用分區、用地編定）：
計畫書幾乎不會寫這些，但它的描述性文字就是推定依據 ——
「淺山丘陵」「坡地」「邊坡」「山村」→ 推定可能位於山坡地；
「休耕農地」「農地」→ 推定為農業用地。
依這種推定判「觸發」，把 confidence 設 medium 或 low，**不要**因為缺法定文件就退成需補資訊。

## verdict 只能是這四種

- 觸發：計畫書有具體內容落入這條的適用情境（含上述合理推定）
- 不觸及：計畫書沒有相關內容，或明顯不適用
- 需補資訊：**僅限**適用與否取決於一個明確的量化門檻（面積、戶數、金額、規模），
  而計畫書沒給那個數字。區位不明不算這一類，區位不明請判「觸發 + 低信心」。
- 需補語料：這條指向另一部法（「應依○○法辦理」），而那部法**不在**下方列出的語料庫清單裡。
  指向的法若在清單裡，代表本次檢核另有批次會處理它 —— 這時請依本條自身的適用情境判定，
  不要判需補語料。

## confidence

- high：計畫書有直接對應的具體內容
- medium：需要一層推定（例如由「淺山丘陵、邊坡」推定為山坡地）
- low：推定鏈較長，或適用與否還牽涉未載明的條件

## evidence 規則

- 必須是**計畫書的原文片段**，逐字抄，最多 50 字，抄最相關的那一句就好
- 不要改寫、不要自己造句、不要一次抄整個章節
- 判「不觸及」時 evidence 留空字串

只輸出 JSON 陣列，不要任何其他文字、不要 markdown 圍欄："""

_USER = """【計畫書全文】
{plan}

【規模門檻（門檻固定，計畫規模請你自己從計畫書抓；抓不到就判需補資訊）】
{thresholds}

【本次檢核語料庫收錄的法規（判「需補語料」前先對照這份清單）】
{corpus}

【本批管制條目｜法領域：{domain}】
{controls}

請對上列 {n} 條**每一條**輸出一筆判定，格式：
[{{"id":<條目id>,"verdict":"觸發|不觸及|需補資訊|需補語料","evidence":"計畫書原文片段","reasoning":"一句話理由","confidence":"high|medium|low"}}]"""


_GATE_PROMPT = """判斷下面這部法規對這份計畫書**是否適用**。

法規：{law}
適用前提：{precondition}
判斷門檻：{threshold}
{note}

【計畫書全文】
{plan}

只回答前提成不成立，不要判斷計畫有沒有違反這部法。
- 成立：計畫書的內容明確達到門檻
- 不成立：計畫書的內容明確未達門檻
- 待確認：計畫書沒給判斷門檻所需的關鍵數字，或給的數字有歧義（例如同時出現數個面積，
  無法確定哪一個才是門檻所指的那個）

只輸出 JSON，不要其他文字：
{{"gate":"成立|不成立|待確認","reasoning":"一句話理由","missing":"待確認時說明缺什麼資料，否則空字串"}}"""


async def _check_gate(llm, plan: str, gate: dict) -> dict:
    """跑一部法規的適用前提。出錯時保守回「待確認」—— 寧可列出來讓人看，也不要靜靜放行或靜靜排除。"""
    try:
        resp = await llm.ainvoke([("human", _GATE_PROMPT.format(
            law=gate.get("law", ""), precondition=gate.get("precondition", ""),
            threshold=gate.get("threshold", ""),
            note=f"補充：{gate['note']}" if gate.get("note") else "", plan=plan))])
        raw = (resp.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        a, b = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[a:b + 1]) if a >= 0 and b >= 0 else {}
    except Exception as e:  # noqa: BLE001
        logger.exception("適用前提判定失敗 law=%s", gate.get("law"))
        data = {"gate": "待確認", "reasoning": f"前提判定失敗（{type(e).__name__}）", "missing": ""}
    verdict = data.get("gate")
    if verdict not in ("成立", "不成立", "待確認"):
        verdict = "待確認"
    return {"law": gate.get("law", ""), "gate": verdict,
            "precondition": gate.get("precondition", ""), "threshold": gate.get("threshold", ""),
            "reasoning": (data.get("reasoning") or "").strip(),
            "missing": (data.get("missing") or "").strip()}


_SCALE_PROMPT = """判斷這份計畫書的規模，是否達到下面這條法規的門檻。

法規：{law} {article}
門檻：{trigger}
{note}

【計畫書全文】
{plan}

只判斷「規模有沒有達到門檻」，不要判斷計畫其他部分是否違法。
- 達到：計畫書的數字明確達到或超過門檻
- 未達到：計畫書的數字明確低於門檻
- 資料不足：計畫書沒有給判斷門檻所需的數字，或給的數字有歧義（例如同時出現數個面積，
  無法確定哪一個才是門檻所指的）

只輸出 JSON，不要其他文字：
{{"scale":"達到|未達到|資料不足","reasoning":"一句話理由","missing":"資料不足時說明缺什麼，否則空字串"}}"""


def _article_key(text: str) -> str:
    """「§52-1」與「第52-1條」正規化成同一個 key，讓 YAML 點名的條文對得上語料。"""
    m = re.search(r"(\d+(?:[-之]\d+)?)", text or "")
    return m.group(1).replace("之", "-") if m else ""


async def _check_scale(llm, plan: str, item: dict) -> dict:
    """單獨跑一條規模門檻。出錯保守回「資料不足」—— 讓它出現在報告裡，不要靜靜消失。"""
    try:
        resp = await llm.ainvoke([("human", _SCALE_PROMPT.format(
            law=item.get("law", ""), article=item.get("article", ""),
            trigger=item.get("trigger", ""),
            note=f"補充：{item['note']}" if item.get("note") else "", plan=plan))])
        raw = (resp.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        a, b = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[a:b + 1]) if a >= 0 and b >= 0 else {}
    except Exception as e:  # noqa: BLE001
        logger.exception("規模門檻判定失敗 %s %s", item.get("law"), item.get("article"))
        data = {"scale": "資料不足", "reasoning": f"判定失敗（{type(e).__name__}）", "missing": ""}
    scale = data.get("scale")
    if scale not in ("達到", "未達到", "資料不足"):
        scale = "資料不足"
    return {"law": item.get("law", ""), "article": item.get("article", ""),
            "article_key": _article_key(item.get("article", "")), "trigger": item.get("trigger", ""),
            "scale": scale, "reasoning": (data.get("reasoning") or "").strip(),
            "missing": (data.get("missing") or "").strip()}


def _fmt_controls(controls: list[dict]) -> str:
    out = []
    for c in controls:
        bits = [f"[id={c['id']}] {c['regulation']} {c['article_no']}（{c['tag']}）",
                f"  觸發情境：{c['situation']}"]
        if c.get("requirement"):
            bits.append(f"  法定要求：{c['requirement']}")
        if c.get("penalty"):
            bits.append(f"  違反效果：{c['penalty']}")
        out.append("\n".join(bits))
    return "\n\n".join(out)


def _parse(raw: str) -> list[dict]:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    a, b = s.find("["), s.rfind("]")
    if a < 0 or b < 0:
        return []
    try:
        data = json.loads(s[a:b + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and "id" in d]


def _batches(controls: list[dict], size: int) -> list[list[dict]]:
    return [controls[i:i + size] for i in range(0, len(controls), size)]


def _verify_evidence(evidence: str, plan: str) -> tuple[str, bool]:
    """證據必須真的出自計畫書。

    模型偶爾會把**法條原文**當證據抄回來（看起來很像引用，實際上是自我循環）。
    這裡做確定性核對：正規化空白後在計畫書裡找不到，就把證據標記為未驗證。
    報告只呈現驗證過的原文，其餘退成理由敘述 —— 免得複核者拿著假引用去對計畫書。
    """
    ev = re.sub(r"\s+", "", evidence or "")
    if not ev:
        return "", True
    if re.sub(r"\s+", "", plan).find(ev) >= 0:
        return evidence.strip(), True
    return evidence.strip(), False


async def _judge_batch(llm, plan: str, domain: str, batch: list[dict],
                       thresholds: str, corpus_laws: str) -> list[dict]:
    resp = await llm.ainvoke([
        ("system", _SYSTEM),
        ("human", _USER.format(plan=plan, thresholds=thresholds or "（無）", corpus=corpus_laws,
                               domain=domain, controls=_fmt_controls(batch), n=len(batch))),
    ])
    by_id = {c["id"]: c for c in batch}
    out: list[dict] = []
    seen: set[int] = set()
    for v in _parse(resp.content or ""):
        try:
            cid = int(v["id"])
        except (TypeError, ValueError):
            continue
        ctrl = by_id.get(cid)
        if ctrl is None or cid in seen:
            continue
        seen.add(cid)
        evidence, verified = _verify_evidence(v.get("evidence") or "", plan)
        verdict, well_formed = _normalize_verdict(v.get("verdict") or "", evidence)
        confidence = v.get("confidence") or "medium"
        if not verified or not well_formed:
            confidence = "low"      # 引用對不上計畫書、或判定值怪異 → 降信心給偽陽性政策處理
        out.append({**ctrl,
                    "verdict": verdict,
                    "evidence": evidence,
                    "evidence_verified": verified,
                    "reasoning": (v.get("reasoning") or "").strip(),
                    "confidence": confidence})
    # 模型漏回的補成「不觸及（未回覆）」—— 覆蓋率的分母不能因為模型偷懶就縮水
    for cid, ctrl in by_id.items():
        if cid not in seen:
            out.append({**ctrl, "verdict": "不觸及", "evidence": "", "evidence_verified": True,
                        "reasoning": "（模型未回覆此條，計入已評估但未判定觸發）",
                        "confidence": "low"})
    return out


async def run_check(
    plan_text: str,
    category: str,
    *,
    model: str | None = None,
    std_name: str = standard.DEFAULT_STANDARD,
    reasoning: str = "none",
    on_progress: ProgressCb = None,
) -> dict:
    """跑完一次檢核，回 {findings, coverage, elapsed}。

    on_progress 每完成一個法領域叫一次，給 Chainlit 的進度列用（Phase C）。
    """
    std = standard.load(std_name)
    # 沒指定就用 YAML 指定的判定模型 —— 別掉回聊天用的預設模型（實測會變成
    # 打 proxy 卻送 gpt-4o-mini，整批 400，報告還是生得出來但全是「判定失敗」）
    model = model or standard.judge_model(std)
    controls = await registry.scope_negative_list(category)
    excluded = await registry.excluded_categories(category)
    # 收錄了但不進判定的（草案未生效 / 全文未取得）—— 報告要交代，不能靜靜消失
    non_judging = await registry.non_judging_regulations()
    stats = await registry.corpus_stats()
    thresholds = standard.scale_thresholds_text(std)
    # judge 一次只看一個法領域的批次，不知道別批收了什麼；不給清單它會把
    # 「應依區域計畫法辦理」誤報成需補語料（區域計畫法其實就在語料庫裡）。
    corpus_laws = "、".join(sorted({c["regulation"] for c in controls}))

    # gpt-5 系列：開 reasoning 就只能 temperature=1（模型限制），判定會跑跑不一樣；
    # reasoning_effort=none 才收得回 temperature=0。判定穩定度對驗收比推理深度重要，
    # 所以預設走 none + temperature=0；要換回推理模式傳 reasoning="low"。
    if reasoning == "none":
        llm = make_llm(alias=model, temperature=0, streaming=False).bind(
            max_completion_tokens=16000, timeout=CALL_TIMEOUT
        )
    else:
        llm = make_llm(alias=model, temperature=1, streaming=False).bind(
            max_completion_tokens=16000, reasoning_effort=reasoning, timeout=CALL_TIMEOUT
        )
    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.time()

    # 適用前提閘門：整部法要先成立前提才進判定（見 YAML applicability_gate）。
    # 前提不成立／待確認 → 該法整組不判，改由報告交代，避免產出一整批
    # 「甲方一句『我們這案不用送審議』就全數作廢」的違規。
    gates = standard.applicability_gates(std)
    gate_results: list[dict] = []
    if gates:
        gate_results = list(await asyncio.gather(*(_check_gate(llm, plan_text, g) for g in gates)))
    gated_out = {g["law"] for g in gate_results if g["gate"] != "成立"}
    if gated_out:
        skipped = [c for c in controls if c["regulation"] in gated_out]
        controls = [c for c in controls if c["regulation"] not in gated_out]
        logger.info("適用前提未成立，略過 %d 條管制條目：%s", len(skipped), "、".join(gated_out))
        for g in gate_results:
            if g["gate"] != "成立":
                mine = [c for c in skipped if c["regulation"] == g["law"]]
                g["skipped_controls"] = len(mine)
                g["law_domain"] = mine[0]["law_domain"] if mine else ""

    groups: dict[str, list[dict]] = {}
    for c in controls:
        groups.setdefault(c["law_domain"], []).append(c)

    async def run_domain(domain: str, items: list[dict]) -> list[dict]:
        async def one(batch: list[dict]) -> list[dict]:
            async with sem:
                try:
                    return await _judge_batch(llm, plan_text, domain, batch,
                                              thresholds, corpus_laws)
                except Exception as e:  # noqa: BLE001
                    logger.exception("judge 失敗 domain=%s: %s", domain, e)
                    # 整批失敗也要留下痕跡，不能讓分母悄悄變小
                    return [{**c, "verdict": "判定失敗", "evidence": "", "evidence_verified": True,
                             "reasoning": f"{type(e).__name__}: {e}", "confidence": "low"}
                            for c in batch]

        results = await asyncio.gather(*(one(b) for b in _batches(items, BATCH_SIZE)))
        merged = [r for rs in results for r in rs]
        if on_progress:
            hit = sum(1 for r in merged if r["verdict"] == "觸發")
            await on_progress({"domain": domain, "total": len(merged), "hit": hit,
                               "done": True, "elapsed": time.time() - t0})
        return merged

    # 規模門檻條文單獨判定（與各法領域平行跑），結果覆寫大批的判定
    scale_items = standard.scale_thresholds(std)
    scale_task = asyncio.gather(*(_check_scale(llm, plan_text, it) for it in scale_items)) \
        if scale_items else None

    all_results = await asyncio.gather(*(run_domain(d, items) for d, items in groups.items()))
    findings = [r for rs in all_results for r in rs]

    scale_checks: list[dict] = list(await scale_task) if scale_task else []
    _SCALE_VERDICT = {"達到": "觸發", "未達到": "不觸及", "資料不足": "需補資訊"}
    for chk in scale_checks:
        for f in findings:
            if f["regulation"] == chk["law"] and _article_key(f["article_no"]) == chk["article_key"]:
                f["verdict"] = _SCALE_VERDICT[chk["scale"]]
                f["reasoning"] = chk["reasoning"] or f.get("reasoning", "")
                f["decided_by"] = "scale_threshold"   # 報告要看得出這條是專門判過的

    for f in findings:
        f["section"], f["severity"] = standard.route(std, f["tag"], f.get("confidence", "high"))

    return {
        "findings": findings,
        # 判定用的模型與參數要跟著結果走：等 golden sample 到位要回頭比對
        # 「哪一次跑用什麼設定」時，不能變成考古。
        "engine": {
            "model": model or "（預設）",
            "temperature": 0 if reasoning == "none" else 1,
            "reasoning_effort": reasoning,
            "batch_size": BATCH_SIZE,
            "concurrency": CONCURRENCY,
        },
        "coverage": {
            "category": category,
            "controls": len(controls),
            "evaluated": len(findings),
            "domains": sorted(groups),
            "excluded_categories": excluded,
            "covered_declared": standard.covered_domains(std),
            "batches": sum(len(_batches(v, BATCH_SIZE)) for v in groups.values()),
            "regulations_active": stats.get("active", 0),
            "gates": gate_results,
            "scale_checks": scale_checks,
            "non_judging": non_judging,
        },
        "standard": std.get("standard", {}),
        "elapsed": time.time() - t0,
    }
