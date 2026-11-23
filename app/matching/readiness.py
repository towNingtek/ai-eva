"""媒合準備度（ai-eva EPIC #176 / #238）：選好 A 的當下先看資料夠不夠，不夠就多問，**永不擋開始**。

- 四項：你能提供什麼（offer）、你需要什麼（need）、規模與時間（scale）、想怎麼合作（collab）。
- 狀態 ok（✅ 足夠）／vague（⚠ 不夠具體）／missing（？ 還沒寫），由既有的能力判斷結果
  （capability.judge / analyze 的 capabilities[Bk].direction）加上計畫理念原文推得，不另做判斷系統。
- 補問最多 3 題，每題 2–4 個選項（另有「其他（自己寫）」）；回答後問要不要補進計畫理念，
  只有使用者同意才走既有的寫回流程（flow.writeback_with_record → writeback.offer_writeback → append_philosophy）。
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Mapping, Optional

from app.matching import i18n as mi
from app.matching import pair

ITEMS = ("offer", "need", "scale", "collab")
OK, VAGUE, MISSING = "ok", "vague", "missing"
STATES = (OK, VAGUE, MISSING)
ICONS = {OK: "✅", VAGUE: "⚠", MISSING: "？"}
MAX_QUESTIONS = 3
ASK_ORDER = ("need", "offer", "scale", "collab")   # 補問先問最影響媒合的

# 原文裡「需要」有細節的線索（說清楚缺什麼、找什麼）
_NEED_DETAIL = re.compile(r"需要|缺乏|缺少|欠缺|尋找|徵求|招募|希望(?:找|有|能有)|期待(?:找|有)|looking for|we need|seeking",
                          re.I)
# 規模與時間
_SCALE = re.compile(
    r"\d+\s*(?:人|位|名|場|次|個|組|年|月|週|周|天|日|小時|萬|元|戶|所|間|團隊|期|件|公頃|坪)"
    r"|規模|預計|期程|時程|為期|每年|每月|每週|每周|長期|短期|年度|季度|半年|今年|明年|20\d\d"
    r"|\b\d+\s*(?:people|participants|months?|weeks?|years?|days?|events?)\b|timeline|annual|monthly|weekly",
    re.I)
# 想怎麼合作
_COLLAB = re.compile(r"合作|共同|聯合|協力|夥伴|伙伴|串連|串聯|共創|共學|交流|協作|結盟|共辦|攜手|一起"
                     r"|partner|collaborat|together|joint", re.I)


def _directions(judged: Mapping | None) -> dict[str, str]:
    caps = (judged or {}).get("capabilities") or {}
    out = {}
    for k in pair.B_KEYS:
        d = (caps.get(k) or {}).get("direction")
        out[k] = d if d in (pair.NEED, pair.OFFER, pair.BOTH) else pair.NONE
    return out


def assess(judged: Mapping | None, philosophy: str = "") -> dict:
    """能力判斷結果＋原文 → {"items": [{"key","state"}…], "complete": bool}。"""
    text = philosophy or ""
    dirs = _directions(judged)
    offers = [k for k, d in dirs.items() if d in (pair.OFFER, pair.BOTH)]
    needs = [k for k, d in dirs.items() if d in (pair.NEED, pair.BOTH)]

    offer = OK if offers else MISSING
    if not needs:
        need = MISSING
    elif len(needs) >= 2 or _NEED_DETAIL.search(text):
        need = OK
    else:
        need = VAGUE
    scale = OK if _SCALE.search(text) else MISSING
    collab = OK if _COLLAB.search(text) else MISSING
    states = {"offer": offer, "need": need, "scale": scale, "collab": collab}
    items = [{"key": k, "state": states[k]} for k in ITEMS]
    return {"items": items, "complete": all(i["state"] == OK for i in items)}


def labels(items, lang: Any = None) -> list[dict]:
    """每項加上顯示文字（依語言）與圖示。"""
    return [{**i, "label": mi.msg(f"readiness.item.{i['key']}", lang), "icon": ICONS[i["state"]],
             "state_text": mi.msg(f"readiness.state.{i['state']}", lang)} for i in items]


def question(key: str, lang: Any = None) -> dict:
    options = [o for o in mi.msg(f"readiness.opt.{key}", lang).split("|") if o]
    return {"key": key, "text": mi.msg(f"readiness.q.{key}", lang), "options": options}


def questions(items, lang: Any = None) -> list[dict]:
    """不足的項目 → 最多 3 題（每題 2–4 個選項）；全部足夠 → []。"""
    weak = {i["key"] for i in items if i.get("state") != OK}
    return [question(k, lang) for k in ASK_ORDER if k in weak][:MAX_QUESTIONS]


def texts(lang: Any = None) -> dict:
    """面板用的固定文字（伺服器依語言給，面板沒有時用自己的四語表）。"""
    return {k: mi.msg(f"readiness.{k}", lang) for k in ("hint", "complete", "ask", "skip", "other", "stop", "consent")}


def build(judged: Mapping | None, philosophy: str, *, a: str, lang: Any = None) -> dict:
    """面板快照用的準備度：四項＋（不足時）補問題目。"""
    res = assess(judged, philosophy)
    return {"a": a, "state": "ready", "complete": res["complete"], "items": labels(res["items"], lang),
            "questions": [] if res["complete"] else questions(res["items"], lang), "texts": texts(lang)}


def writeback_text(key: str, answer: str) -> str:
    """寫回計畫理念的內容（不翻：項目名稱用中文）。"""
    return f"{mi.msg(f'readiness.item.{key}', 'zh')}：{(answer or '').strip()}"


Writeback = Callable[..., Awaitable[dict]]


async def answer(runtime, *, uuid: str, key: str, answer: str, consent: bool,
                 writeback: Optional[Writeback] = None, run_id: Optional[int] = None) -> dict:
    """補問的一個回答。沒同意 → 什麼都不寫；同意 → 走既有寫回流程（使用者已在面板按了同意）。"""
    if key not in ITEMS or not (answer or "").strip():
        return {"result": "invalid", "uuid": uuid}
    if consent is not True:
        return {"result": "declined", "asked": True, "uuid": uuid}
    if writeback is None:
        from app.matching import flow

        writeback = flow.writeback_with_record
    return await writeback(runtime, run_id, uuid=uuid, question=mi.msg(f"readiness.q.{key}", "zh"),
                           answer=writeback_text(key, answer), ask=lambda _prompt: True)


__all__ = ["ITEMS", "OK", "VAGUE", "MISSING", "MAX_QUESTIONS", "assess", "labels", "question", "questions",
           "texts", "build", "writeback_text", "answer"]
