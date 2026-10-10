"""CMS 專案填寫助手（town-intelligent/swarm#389 步驟 4）。

CMS 後端（已驗證 project.write）把專案內容與使用者問題送來，這裡請 LLM 回
「回覆文字＋可套用的建議」。**不寫入任何東西**：建議由使用者在 CMS 按「套用」後，
CMS 前端走原本的儲存 API 寫入。服務 token 與 /internal/sdg/generate 共用。
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from chainlit.server import app as fastapi_app

from app.core.llm import make_llm
from app.surfaces.sdg import _check_service_token

logger = logging.getLogger(__name__)

MAX_MESSAGE = 1000
MAX_HISTORY = 8
STEPS = {"basic", "sdgs", "impact", "contact", "sroi", "review"}

SYSTEM = """你是「專案填寫助手」，協助台灣地方團隊在永續專案後台填寫專案資料。用繁體中文、口語、簡短回答（150 字內，必要時條列）。

你看得到目前專案內容（JSON）與使用者所在步驟。你**不能直接修改**任何資料，只能提出建議；使用者按「套用」才會寫入。

可以提出的建議種類（只有這些）：
- philosophy：計畫理念全文（100~300 字，具體寫出問題、對象、做法、預期改變；不知道的數字用（請填入…）標示，不要捏造）
- sdgs：建議加入的 SDG 編號陣列（1~17，最多 6 個，只放真正相關的）
- sdg_texts：物件 {"SDG編號":"這個專案如何推進該 SDG，約 40~80 字"}，只寫專案已選或你同時建議的 SDG
- tasks：建議新增的活動陣列 [{"name":"活動名稱（20 字內）","overview":"一兩句說明"}]，最多 5 個

規則：
- 使用者只是問問題或閒聊時，不要給建議（suggestions 給空物件）。
- 不要覆蓋使用者已經寫好的內容：sdg_texts 只寫目前空白的 SDG，除非使用者明確要求重寫。
- 不知道的事實不要編；SROI 的實際數字一定要使用者自己填，你只能解釋指標、提醒要準備哪些佐證。
- 只回 JSON：{"reply":"給使用者看的回覆","suggestions":{...可省略的鍵...}}，不要其他文字。"""


def _parse(text: str) -> dict:
    if not text:
        return {}
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return {}
    try:
        # strict=False: models often put raw newlines inside JSON strings.
        data = json.loads(text[s:e + 1], strict=False)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


_REPLY = re.compile(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', re.S)


def _fallback_reply(text: str) -> str:
    """Model answered in broken JSON: salvage "reply", never show raw JSON."""
    m = _REPLY.search(text or "")
    if m:
        try:
            return json.loads(f'"{m.group(1)}"', strict=False)
        except json.JSONDecodeError:
            return m.group(1)
    t = (text or "").strip()
    return "" if t.startswith("{") or t.startswith("```") else t


def clean_suggestions(raw) -> dict:
    """白名單 + 長度上限。CMS 端會再驗一次。"""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    ph = raw.get("philosophy")
    if isinstance(ph, str) and 0 < len(ph.strip()) <= 2000:
        out["philosophy"] = ph.strip()
    sdgs = raw.get("sdgs")
    if isinstance(sdgs, list):
        nums = sorted({int(n) for n in sdgs if str(n).strip().isdigit() and 1 <= int(n) <= 17})
        if 0 < len(nums) <= 6:
            out["sdgs"] = nums
    texts = raw.get("sdg_texts")
    if isinstance(texts, dict):
        t = {str(int(k)): v.strip() for k, v in texts.items()
             if str(k).strip().isdigit() and 1 <= int(k) <= 17 and isinstance(v, str) and 0 < len(v.strip()) <= 1000}
        if t:
            out["sdg_texts"] = t
    tasks = raw.get("tasks")
    if isinstance(tasks, list):
        items = []
        for x in tasks[:5]:
            if not isinstance(x, dict):
                continue
            name = str(x.get("name") or "").strip()[:30]
            overview = str(x.get("overview") or "").strip()[:500]
            if name:
                items.append({"name": name, "overview": overview})
        if items:
            out["tasks"] = items
    return out


def _history(raw) -> list:
    msgs = []
    for m in (raw if isinstance(raw, list) else [])[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        text = str(m.get("text") or "")[:MAX_MESSAGE]
        if not text:
            continue
        msgs.append(AIMessage(content=text) if m.get("who") == "ai" else HumanMessage(content=text))
    return msgs


async def ask(project: dict, step: str, message: str, history: list, *, user: str = "") -> dict:
    llm = make_llm(user=user, streaming=False, temperature=0.4)
    context = json.dumps({"step": step, "project": project}, ensure_ascii=False)
    resp = await llm.ainvoke([
        SystemMessage(content=SYSTEM),
        SystemMessage(content=f"目前專案內容與步驟：{context}"),
        *_history(history),
        HumanMessage(content=message),
    ])
    data = _parse(resp.content or "")
    reply = str(data.get("reply") or "").strip()
    if not reply:
        # 模型沒照格式回：撈出 reply 或用原文（純文字時），不給建議
        reply = _fallback_reply(resp.content or "") or "抱歉，我這次沒有整理好，請再問一次。"
        return {"reply": reply[:1500], "suggestions": {}}
    return {"reply": reply[:1500], "suggestions": clean_suggestions(data.get("suggestions"))}


@fastapi_app.post("/internal/cms/copilot")
async def cms_copilot_endpoint(request: Request):
    _check_service_token(request)
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(400, "body must be an object")
    message = str(data.get("message") or "").strip()
    if not message or len(message) > MAX_MESSAGE:
        raise HTTPException(400, "message is required (max 1000 chars)")
    project = data.get("project")
    if not isinstance(project, dict):
        raise HTTPException(400, "project is required")
    step = data.get("step") if data.get("step") in STEPS else "basic"
    try:
        return await ask(project, step, message, data.get("history") or [], user=str(data.get("user_id") or ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("cms copilot failed: %s", type(exc).__name__)
        raise HTTPException(502, f"copilot failed: {type(exc).__name__}") from exc
