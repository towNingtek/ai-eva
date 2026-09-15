"""SDG module handler — 從 copilot.py 搬出（#129：邏輯搬家、adapter 介面）。

原本 cosy 在 copilot.py 的 generate_and_save_sdg：讀專案資訊 → LLM 產 {SDG:描述}
→ save_sdg。這裡改成 module，唯一的差別是「資料後端」走 ctx.data（adapter），
不再直接 execute runtime —— context（uuid）由呼叫端注入，module 不寫死。

判準（(c) 卡）：換 SDG module 的資料後端（CMS ↔ stub）→ 邏輯零修改，僅 adapter 換檔。
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.base import ModuleContext, result

_SDG_PROMPT = (
    "你是 SDG 顧問。根據專案資訊，從聯合國 17 個 SDG 中挑出 **3~6 個最相關的**，"
    "為每個寫一句『這專案如何推進該 SDG』的繁體中文描述（約 30~60 字）。"
    "只放真的命中的，別硬湊。**只回 JSON 物件** {\"SDG編號(字串1~17)\":\"描述\"}，不要其他文字。"
)


def _parse_json_obj(text: str) -> dict:
    if not text:
        return {}
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return {}
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return {}


async def _generate(ctx: ModuleContext, payload: dict) -> dict:
    """payload: {project_info: dict, uuid: str}（uuid 由呼叫端注入，不寫死）。"""
    project_info = payload.get("project_info") or {}
    uuid = payload.get("uuid") or ""
    if not uuid:
        return result(False, "缺少要寫的專案 uuid", error="missing uuid")
    llm = ctx.llm
    if llm is None:
        return result(False, "此環境未注入 LLM，無法產 SDG", error="no llm")
    resp = await llm.ainvoke([
        SystemMessage(content=_SDG_PROMPT),
        HumanMessage(content=json.dumps(project_info, ensure_ascii=False)),
    ])
    sdgs = _parse_json_obj(getattr(resp, "content", "") or "")
    sdgs = {str(k): v for k, v in sdgs.items() if str(k).isdigit() and v}
    if not sdgs:
        return result(False, "（SDG 自動產生失敗，可稍後再說「幫我產 SDG」重試）")

    from app.adapters.base import QuerySpec
    res = await ctx.data.query(
        QuerySpec(tool="save_sdg", args={"uuid": uuid, "project_sdgs": sdgs}, confirmed=True)
    )
    if res.status != "ok":
        return result(False, f"（SDG 儲存失敗：{res.reason}）")
    return result(
        True,
        "已自動產生並存好 SDG：" + "、".join(f"SDG {k}" for k in sorted(sdgs, key=int)),
        {"sdgs": sdgs},
    )


async def handle(ctx: ModuleContext, payload: dict) -> dict:
    action = ctx.action or "generate"
    if action == "generate":
        return await _generate(ctx, payload)
    return result(False, f"未支援的 sustainability.sdg action：{action}")