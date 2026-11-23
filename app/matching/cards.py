"""媒合建議卡 Top 3–5（ai-eva #202，MVP 步驟 8）。

依媒合引擎（#200 engine.match）的結果出卡：
- 最多 min(5, 對象數) 張，依排序名次；被硬條件排除的對象不出卡。
- 每張卡六個欄位：為何推薦、互補性、互惠價值、建議合作、待確認、風險；沒有依據的欄位寫「不足」，不臆測。
- 「為何推薦」比照法規揭露規則：由程式寫出是哪條排序規則成立（名稱＋規則原文），
  以及對應雙方哪段原文（只採逐字存在於該計畫 philosophy 的片段）；不是黑箱分數。
- 附「合作起步草案」：下一步選項（介紹、會議、資料交換、小型 Pilot），由發起人決定。
- LLM 只對排序前 N 名（top_n）各呼叫一次寫白話理由；其餘卡用程式依引擎結果組字。
- 第一期未評估的四維在卡上標「未評估」。
- 全卡白話、不出現能力類別代號（B1–B8），一律換成類別中文名稱。

提示詞在 app/matching/prompts/cards.md。LLM 可注入（測試用假物件）：
    build_cards(result, projects, llm=fake, top_n=3)
llm 可以是 callable(messages) -> str，或有 .invoke(messages) 的 LangChain chat model。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.matching import engine as eng
from app.matching import pair

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
PROMPT = HERE / "prompts" / "cards.md"

MAX_CARDS = 5
DEFAULT_TOP_N = 3
INSUFFICIENT = "不足"
NOT_EVALUATED = "未評估"

F_WHY, F_COMPLEMENT, F_RECIPROCITY, F_COLLAB, F_CONFIRM, F_RISK = (
    "為何推薦", "互補性", "互惠價值", "建議合作", "待確認", "風險")
FIELDS = (F_WHY, F_COMPLEMENT, F_RECIPROCITY, F_COLLAB, F_CONFIRM, F_RISK)
LLM_FIELDS = FIELDS[1:]

NEXT_STEPS = (
    {"id": "introduce", "name": "介紹", "說明": "由平台或發起人寄出雙方簡介，先認識彼此"},
    {"id": "meeting", "name": "會議", "說明": "約一次線上或現場會談，確認需求與可提供的內容"},
    {"id": "data_exchange", "name": "資料交換", "說明": "交換計畫書、場地或產品資料，評估是否合適"},
    {"id": "pilot", "name": "小型 Pilot", "說明": "挑一件小事試做一次，再決定是否擴大合作"},
)

B_CODE = re.compile(r"B[1-8](?![0-9])")
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.S)
_USER_MARK = "<!-- user -->"


# ── 白話化 ───────────────────────────────────────────────────────────

def _bnames(std: Mapping | None = None) -> dict[str, str]:
    std = std if std is not None else pair.load_standard()
    reg = std.get("capability_registry") or {}
    return {k: (reg.get(k) or {}).get("名稱") or "能力" for k in pair.B_KEYS}


def plain(text: Any, names: Mapping[str, str] | None = None) -> str:
    """把 B1–B8 代號換成中文類別名稱；「B1–B8」這種範圍寫法換成「各類能力」。"""
    names = names or _bnames()
    s = str(text or "")
    s = re.sub(r"B[1-8]\s*[–\-~～]\s*B[1-8]", "各類能力", s)
    return B_CODE.sub(lambda m: names.get(m.group(0), "能力"), s)


def _plain_all(obj: Any, names: Mapping[str, str]) -> Any:
    if isinstance(obj, str):
        return plain(obj, names)
    if isinstance(obj, Mapping):
        return {plain(k, names): _plain_all(v, names) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain_all(v, names) for v in obj]
    return obj


def has_b_code(text: str) -> bool:
    return bool(B_CODE.search(text or ""))


# ── 原文 ─────────────────────────────────────────────────────────────

def _verbatim(quotes: Sequence[str], philosophy: str) -> list[str]:
    """只留逐字存在於 philosophy 的原文；不在的丟掉（不臆測）。"""
    out = []
    for q in quotes or []:
        q = str(q or "").strip()
        if q and philosophy and q in philosophy and q not in out:
            out.append(q)
        elif q:
            logger.warning("cards: 原文不在 philosophy 中，不採用：%s", q)
    return out


def _quote_list(qs: Sequence[str]) -> str:
    return "、".join(f"「{q}」" for q in qs)


# ── LLM ──────────────────────────────────────────────────────────────

def load_prompt(path: Path | str = PROMPT) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"^\s*<!--(?!\s*user\s*-->).*?-->\s*", "", text, count=1, flags=re.S)
    system, _, user = text.partition(_USER_MARK)
    return {"system": system.strip(), "user": user.strip()}


def build_messages(context: Mapping, *, prompt: Mapping | None = None) -> list[dict]:
    prompt = prompt if prompt is not None else load_prompt()
    ctx = json.dumps(context, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": prompt["user"].replace("{{context}}", ctx)},
    ]


def _call(llm: Any, messages: list[dict]) -> Any:
    if hasattr(llm, "invoke"):
        out = llm.invoke([(m["role"], m["content"]) for m in messages])
        return getattr(out, "content", out)
    return llm(messages)


def _default_llm():
    from app.core.llm import make_llm  # 延後載入：測試注入假物件時不需要 langchain / LiteLLM 設定

    return make_llm(temperature=0, streaming=False, json_mode=True)


def parse_reply(reply: Any) -> dict:
    if isinstance(reply, dict):
        return reply
    text = _FENCE.sub("", str(reply or "")).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
    return data if isinstance(data, dict) else {}


# ── 各欄位（程式組字，依引擎結果） ──────────────────────────────────

def _side_name(pid: str, a_id: str, a_name: str, t_name: str) -> str:
    return a_name if pid == a_id else t_name


def _why(rank_entry: Mapping, result_entry: Mapping, a: Mapping, t: Mapping, names: Mapping) -> tuple[str, dict]:
    """為何推薦：成立的排序規則（名稱＋原文）＋雙方對應原文。回傳（文字, 結構化揭露）。"""
    a_name, t_name = a.get("name") or "發起計畫", t.get("name") or "對象計畫"
    a_phil, t_phil = str(a.get("philosophy") or ""), str(t.get("philosophy") or "")
    no = result_entry["dimensions"][eng.DIM_NEED_OFFER]
    rules = [r for r in rank_entry.get("rules") or [] if r.get("rule") != "input_order"]
    met = [r for r in rules if (r.get("value") or 0) > 0]
    decided = rank_entry.get("decided_by")

    evidence = []
    for item in list(no.get("a_needs_target_offers") or []) + list(no.get("target_needs_a_offers") or []):
        need_p, offer_p = (a, t) if item["need"] == str(a["id"]) else (t, a)
        need_q = _verbatim(item.get("need_evidence") or [], str(need_p.get("philosophy") or ""))
        offer_q = _verbatim(item.get("offer_evidence") or [], str(offer_p.get("philosophy") or ""))
        evidence.append({
            "類別": names.get(item["key"], "能力"),
            "需要方": need_p.get("name") or "", "需要方原文": need_q,
            "提供方": offer_p.get("name") or "", "提供方原文": offer_q,
        })
    a_quotes = [q for e in evidence for side in ("需要方", "提供方")
                if e[side] == a_name for q in e[f"{side}原文"]]
    t_quotes = [q for e in evidence for side in ("需要方", "提供方")
                if e[side] == t_name for q in e[f"{side}原文"]]
    a_quotes = [q for q in dict.fromkeys(a_quotes) if q in a_phil]
    t_quotes = [q for q in dict.fromkeys(t_quotes) if q in t_phil]

    disclosure = {"成立規則": [{"規則": r["name"], "原文": r.get("原文", ""), "數值": r.get("value"),
                              "結果": {"bidirectional": no.get("verdict", ""),
                                     "complement_count": result_entry["dimensions"][eng.DIM_B1_B8].get(
                                         "verdict", "")}.get(r.get("rule"), "")}
                             for r in met],
                  "排序依據": ({"規則": decided.get("name", ""), "原文": decided.get("原文", "")}
                           if decided else None),
                  "雙方原文": {a_name: a_quotes, t_name: t_quotes},
                  "對應": evidence}

    if not met:
        return INSUFFICIENT, _plain_all(disclosure, names)
    outcome = {"bidirectional": no.get("verdict", ""),
               "complement_count": result_entry["dimensions"][eng.DIM_B1_B8].get("verdict", "")}
    parts = []
    for r in met:
        res = outcome.get(r.get("rule"), "")
        parts.append(f"依規則「{r['name']}」（規則原文：{r.get('原文', '')}），本組結果為{res or '成立'}")
    text = "；".join(parts) + "。"
    lines = []
    for e in evidence:
        if e["需要方原文"] or e["提供方原文"]:
            need_txt = _quote_list(e["需要方原文"]) or INSUFFICIENT
            offer_txt = _quote_list(e["提供方原文"]) or INSUFFICIENT
            lines.append(f"{e['類別']}：{e['需要方']}原文{need_txt}，{e['提供方']}原文{offer_txt}")
    text += ("對應原文——" + "；".join(lines) + "。") if lines else "雙方原文依據不足。"
    if decided and decided.get("name"):
        text += f"排在第 {rank_entry['rank']} 名，依據規則「{decided['name']}」。"
    return plain(text, names), _plain_all(disclosure, names)


def _complement(no: Mapping, a_name: str, t_name: str, names: Mapping) -> str:
    a_gets = [names.get(x["key"], "能力") for x in no.get("a_needs_target_offers") or []]
    t_gets = [names.get(x["key"], "能力") for x in no.get("target_needs_a_offers") or []]
    parts = []
    if a_gets:
        parts.append(f"{a_name}需要的{'、'.join(a_gets)}，{t_name}能提供")
    if t_gets:
        parts.append(f"{t_name}需要的{'、'.join(t_gets)}，{a_name}能提供")
    return ("；".join(parts) + "。") if parts else INSUFFICIENT


def _reciprocity(no: Mapping, a_name: str, t_name: str, names: Mapping) -> str:
    a_gets = [names.get(x["key"], "能力") for x in no.get("a_needs_target_offers") or []]
    t_gets = [names.get(x["key"], "能力") for x in no.get("target_needs_a_offers") or []]
    if a_gets and t_gets:
        return (f"雙向互惠：{a_name}得到{'、'.join(a_gets)}的支援，"
                f"{t_name}得到{'、'.join(t_gets)}的支援。")
    return INSUFFICIENT


def _to_confirm(b: Mapping, no: Mapping, a: Mapping, t: Mapping, names: Mapping) -> str:
    items = []
    for x in list(no.get("a_needs_target_offers") or []) + list(no.get("target_needs_a_offers") or []):
        offer_p = t if x["offer"] == str(t["id"]) else a
        if not _verbatim(x.get("offer_evidence") or [], str(offer_p.get("philosophy") or "")):
            items.append(f"{offer_p.get('name') or '對方'}能否實際提供{names.get(x['key'], '能力')}（原文未寫明）")
    third = [names.get(k, "能力") for k in b.get("third_party") or []]
    if third:
        items.append(f"雙方都需要{'、'.join(third)}，是否要共同找第三方")
    return ("；".join(items) + "。") if items else INSUFFICIENT


def _fallback_fields(result_entry: Mapping, a: Mapping, t: Mapping, names: Mapping) -> dict:
    a_name, t_name = a.get("name") or "發起計畫", t.get("name") or "對象計畫"
    dims = result_entry["dimensions"]
    no, b = dims[eng.DIM_NEED_OFFER], dims[eng.DIM_B1_B8]
    return {
        F_COMPLEMENT: _complement(no, a_name, t_name, names),
        F_RECIPROCITY: _reciprocity(no, a_name, t_name, names),
        F_COLLAB: INSUFFICIENT,
        F_CONFIRM: _to_confirm(b, no, a, t, names),
        F_RISK: INSUFFICIENT,
    }


def _context(result_entry: Mapping, a: Mapping, t: Mapping, fields: Mapping, why: Mapping,
             not_evaluated: Mapping) -> dict:
    """給 LLM 的內容：已白話化、不含代號。"""
    return {
        "發起計畫": a.get("name") or "", "對象計畫": t.get("name") or "",
        "互補判斷": result_entry["dimensions"][eng.DIM_NEED_OFFER]["verdict"],
        "推薦依據": why,
        "程式整理": dict(fields),
        "未評估面向": [v.get("name", k) for k, v in not_evaluated.items()],
    }


# ── 主流程 ───────────────────────────────────────────────────────────

def _project_map(projects: Mapping | Sequence[Mapping]) -> dict[str, Mapping]:
    if isinstance(projects, Mapping):
        if "id" in projects and not isinstance(projects.get("id"), Mapping):
            return {str(projects["id"]): projects}
        return {str(k): v for k, v in projects.items()}
    return {str(p["id"]): p for p in projects}


def card_count(result: Mapping) -> int:
    return min(MAX_CARDS, len(result.get("targets") or []), len(result.get("ranking") or []))


def build_cards(
    result: Mapping,
    projects: Mapping | Sequence[Mapping],
    *,
    llm: Any | Callable[[list[dict]], Any] | None = None,
    top_n: int = DEFAULT_TOP_N,
    prompt: Mapping | None = None,
    std: Mapping | None = None,
) -> list[dict]:
    """engine.match() 的結果 → 媒合建議卡（依名次，最多 min(5, 對象數) 張）。

    projects：A 與各對象（list 或 {id: project}），需含 name、philosophy。
    llm：只對前 top_n 名各呼叫一次；None 且 top_n > 0 時用預設模型。
    """
    names = _bnames(std)
    pmap = _project_map(projects)
    a = pmap.get(str(result["a"])) or {"id": result["a"], "name": "發起計畫", "philosophy": ""}
    by_target = {r["target"]: r for r in result.get("results") or []}
    not_evaluated = result.get("not_evaluated") or {}
    n_cards = card_count(result)
    n_llm = max(0, min(int(top_n), n_cards))
    if n_llm and llm is None:
        llm = _default_llm()

    cards = []
    for rank_entry in list(result.get("ranking") or [])[:n_cards]:
        tid = rank_entry["target"]
        res = by_target[tid]
        t = pmap.get(tid) or {"id": tid, "name": res.get("name", tid), "philosophy": ""}
        t = {**t, "name": t.get("name") or res.get("name") or "對象計畫"}
        why_text, why = _why(rank_entry, res, a, t, names)
        fields = _fallback_fields(res, a, t, names)
        used_llm = rank_entry["rank"] <= n_llm
        if used_llm:
            reply = parse_reply(_call(llm, build_messages(
                _context(res, a, t, fields, why, not_evaluated), prompt=prompt)))
            for f in LLM_FIELDS:
                v = str(reply.get(f) or "").strip()
                fields[f] = plain(v, names) if v else INSUFFICIENT
        fields = {F_WHY: why_text, **{f: (plain(fields[f], names).strip() or INSUFFICIENT) for f in LLM_FIELDS}}
        cards.append({
            "rank": rank_entry["rank"],
            "target": tid,
            "name": t["name"],
            "fields": fields,
            "推薦依據": why,
            "未評估": {v.get("name", k): NOT_EVALUATED for k, v in not_evaluated.items()},
            "合作起步草案": {
                "說明": "以下是可選的下一步，由發起人決定要不要做、先做哪一項",
                "決定者": "發起人",
                "選項": [dict(s) for s in NEXT_STEPS],
            },
            "llm": used_llm,
        })
    return cards


def render(card: Mapping) -> str:
    """把一張卡輸出成白話文字（給畫面或檢查用）。"""
    lines = [f"第 {card['rank']} 名：{card['name']}"]
    for f in FIELDS:
        lines.append(f"【{f}】{card['fields'][f]}")
    if card.get("未評估"):
        lines.append("【未評估】" + "、".join(f"{k}：{v}" for k, v in card["未評估"].items()))
    draft = card["合作起步草案"]
    lines.append(f"【合作起步草案】{draft['說明']}：" + "、".join(s["name"] for s in draft["選項"]))
    return "\n".join(lines)
