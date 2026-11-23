"""指定媒合：兩個專案的 B1–B8 結果 → 關係與狀態，資料不足時接多輪狀態機追問（ai-eva #183）。

移植自 ai-eva-tangle-lab ff77f17 app/lab/tangle_lab.py 的 complement_pairs／match_status_for／next_question_for。
規則全部來自媒合標準 YAML（standard_yunlin_v1.yaml，v1.1）：

- 關係（bridge_rules）：
  - 互補候選：一方 NEED／BOTH × 另一方 OFFER／BOTH，同一類；BOTH 兩邊都算（兩個方向各一條）。
  - 共同尋找第三方：同一類兩邊都只 NEED（不算互補）。
  - 可聯合或交流：同一類兩邊都只 OFFER（不是互補）。
- 狀態（status_rules＋status_transition）：
  - 有互補候選 → CLARIFY_FIRST；任一候選補齊需要方「用途」與能提供方「可提供形式」→ EXPLORE。
  - 沒有互補但有兩邊都 OFFER → EXPLORE。
  - 都沒有 → ELIGIBLE。
  - 第一期不開放 RECOMMEND（Q4），永遠不會輸出。
- 補問（clarify_questions）：每一條互補候選是一個多輪狀態機（app.loop，#177），
  先問所有候選的 minimum_fields（需要方「用途」→ 能提供方「可提供形式」），再問其他欄位；一次一題。
  「還不知道」會記下，但不算補齊。

輸入的 B1–B8 結果可以是 capability.analyze() 的輸出（{"capabilities": {"B1": {"direction": ...}}}），
或簡單的 {"B1": "NEED", ...}／{"B1": {"direction": "NEED"}}。
回答以 "pid:key:field" 為鍵（如 "a:B3:用途"）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from app.loop import Rules

HERE = Path(__file__).resolve().parent
STANDARD = HERE / "standard_yunlin_v1.yaml"

B_KEYS = [f"B{i}" for i in range(1, 9)]
NEED, OFFER, BOTH, NONE = "NEED", "OFFER", "BOTH", "none"

CLARIFY_FIRST, EXPLORE, ELIGIBLE, RECOMMEND = "CLARIFY_FIRST", "EXPLORE", "ELIGIBLE", "RECOMMEND"
STATUS_TEXT = {CLARIFY_FIRST: "先補資料", EXPLORE: "可探索", ELIGIBLE: "可排序・未建議", "EXCLUDED": "不在範圍"}
REL_COMPLEMENT, REL_THIRD_PARTY, REL_PEER = "互補候選", "共同尋找第三方", "可聯合或交流"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_standard(path: Path | str = STANDARD) -> dict:
    return _load(str(path))


def _std(std: Mapping | None) -> Mapping:
    return std if std is not None else load_standard()


def candidate_rules(std: Mapping | None = None) -> Rules:
    """一條互補候選的多輪狀態機規則：CLARIFY_FIRST → EXPLORE，最低欄位與題目都取自 YAML。"""
    std = _std(std)
    spec = {
        "status_transition": {
            "from": CLARIFY_FIRST,
            "to": EXPLORE,
            "minimum_fields": dict(std["status_transition"]["minimum_fields"]),
            "unknown_counts_as_filled": False,
        },
        "clarify_questions": {side: dict(std["clarify_questions"][side]) for side in (NEED, OFFER)},
    }
    return Rules(spec)


# ── 輸入正規化 ─────────────────────────────────────────────────────────

def directions(result: Mapping | None) -> dict[str, str]:
    """B1–B8 結果 → {Bk: NEED/OFFER/BOTH/none}；缺的類別視為 none（不臆測）。"""
    result = result or {}
    caps = result.get("capabilities", result) if isinstance(result, Mapping) else {}
    out = {}
    for k in B_KEYS:
        v = caps.get(k) if isinstance(caps, Mapping) else None
        if isinstance(v, Mapping):
            v = v.get("direction", v.get("role"))
        d = str(v).strip().upper() if v is not None else ""
        out[k] = d if d in (NEED, OFFER, BOTH) else NONE
    return out


def _is_need(d: str) -> bool:
    return d in (NEED, BOTH)


def _is_offer(d: str) -> bool:
    return d in (OFFER, BOTH)


def _names(std: Mapping) -> dict[str, str]:
    reg = std.get("capability_registry") or {}
    return {k: (reg.get(k) or {}).get("名稱", k) for k in B_KEYS}


# ── 關係 ──────────────────────────────────────────────────────────────

def complement_pairs(a_id: str, a: Mapping, b_id: str, b: Mapping) -> list[tuple[str, str, str]]:
    """互補候選：[(need_pid, offer_pid, key)]，BOTH 兩邊都算。"""
    A, B = directions(a), directions(b)
    out = []
    for k in B_KEYS:
        if _is_need(A[k]) and _is_offer(B[k]):
            out.append((a_id, b_id, k))
        if _is_need(B[k]) and _is_offer(A[k]):
            out.append((b_id, a_id, k))
    return out


def third_party_keys(a: Mapping, b: Mapping) -> list[str]:
    """兩邊都只 NEED 的類別：共同尋找第三方，不算互補。"""
    A, B = directions(a), directions(b)
    return [k for k in B_KEYS if A[k] == NEED and B[k] == NEED]


def peer_keys(a: Mapping, b: Mapping) -> list[str]:
    """兩邊都 OFFER、且不是互補的類別：可聯合或交流。"""
    A, B = directions(a), directions(b)
    return [k for k in B_KEYS if A[k] == OFFER and B[k] == OFFER]


def relations(a_id: str, a: Mapping, b_id: str, b: Mapping) -> dict[str, list]:
    return {
        REL_COMPLEMENT: [{"need": n, "offer": o, "key": k} for n, o, k in complement_pairs(a_id, a, b_id, b)],
        REL_THIRD_PARTY: third_party_keys(a, b),
        REL_PEER: peer_keys(a, b),
    }


# ── 狀態 ──────────────────────────────────────────────────────────────

def _facts(need: str, offer: str, key: str, answers: Mapping[str, Any], std: Mapping) -> dict:
    """一條候選的事實：需要方欄位取 need 的回答，能提供方欄位取 offer 的回答。"""
    cq = std["clarify_questions"]
    facts = {}
    for side, pid in ((NEED, need), (OFFER, offer)):
        for f in cq[side]:
            qid = f"{pid}:{key}:{f}"
            if qid in answers:
                facts[f] = answers[qid]
    return facts


def candidate_state(need: str, offer: str, key: str, answers: Mapping[str, Any] | None = None,
                    std: Mapping | None = None) -> str:
    std = _std(std)
    return candidate_rules(std).state(_facts(need, offer, key, answers or {}, std))


def match_status(a_id: str, a: Mapping, b_id: str, b: Mapping,
                 answers: Mapping[str, Any] | None = None, std: Mapping | None = None) -> str:
    """一組計畫的狀態，只用規則；永遠不回 RECOMMEND（第一期不開放）。"""
    std, answers = _std(std), answers or {}
    comp = complement_pairs(a_id, a, b_id, b)
    if comp:
        rules = candidate_rules(std)
        done = any(rules.state(_facts(n, o, k, answers, std)) == EXPLORE for n, o, k in comp)
        status = EXPLORE if done else CLARIFY_FIRST
    elif peer_keys(a, b):
        status = EXPLORE
    else:
        status = ELIGIBLE
    assert status != RECOMMEND
    return status


# ── 補問 ──────────────────────────────────────────────────────────────

def next_question(a_id: str, a: Mapping, b_id: str, b: Mapping,
                  answers: Mapping[str, Any] | None = None, asked: Iterable[str] = (),
                  names: Mapping[str, str] | None = None, key: str | None = None,
                  std: Mapping | None = None) -> dict | None:
    """下一題（一次一題）：先問所有候選的最低欄位（需要方「用途」→ 能提供方「可提供形式」），再問其他。
    answers：已答（含「還不知道」）的 "pid:key:field"；asked：已問過或跳過的 qid。key：只問這一類。"""
    std, answers = _std(std), answers or {}
    done = set(asked) | set(answers)
    names = {a_id: a_id, b_id: b_id, **(names or {})}
    bname = _names(std)
    rules = candidate_rules(std)
    comp = [c for c in complement_pairs(a_id, a, b_id, b) if key is None or c[2] == key]
    mins = [q for q in rules.questions if q.minimum]
    rest = [q for q in rules.questions if not q.minimum]
    order = []
    for qs in (mins, rest):
        for n, o, k in comp:
            for q in qs:
                order.append((n if q.group == NEED else o, n, o, k, q))
    for pid, n, o, k, q in order:
        qid = f"{pid}:{k}:{q.field}"
        if qid in done:
            continue
        text = q.text.format(need=names[n], offer=names[o], b=bname[k])
        return {"id": qid, "pid": pid, "key": k, "side": q.group, "field": q.field,
                "text": text, "minimum": q.minimum}
    return None


def analyze_pair(a_id: str, a: Mapping, b_id: str, b: Mapping,
                 answers: Mapping[str, Any] | None = None, asked: Iterable[str] = (),
                 names: Mapping[str, str] | None = None, std: Mapping | None = None) -> dict:
    """指定媒合的完整輸出：關係、狀態、下一題。"""
    std = _std(std)
    status = match_status(a_id, a, b_id, b, answers, std)
    return {
        "status": status,
        "status_text": STATUS_TEXT[status],
        "relations": relations(a_id, a, b_id, b),
        "next_question": next_question(a_id, a, b_id, b, answers, asked, names, std=std),
    }
