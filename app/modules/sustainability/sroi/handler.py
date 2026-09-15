"""SROI module handler — 從 copilot.py 搬出（#129）。

estimate_and_save_sroi 的 module 版：取指標表（優先 get_sroi_template，退回 get_sroi）
→ LLM 估草稿值 → save_sroi。資料後端一律走 ctx.data（adapter），uuid 由呼叫端注入。
同樣保留 save_sroi 的 encoding=json 需求（由 adapter query spec 帶下去）。
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.adapters.base import QuerySpec
from app.modules.base import ModuleContext, result

_SROI_PROMPT = (
    "你是 SROI 估算顧問。下面有專案資訊與 SROI 指標表（每個指標含『輸入欄標籤』）。"
    "請根據專案資訊，為**能合理對應**的指標估出輸入欄的草稿數字（依標籤由左到右、跳過公式欄）。"
    "只填有把握的指標、其餘留空，數字是粗估草稿。**只回 JSON** "
    "{\"social\":{\"S-1\":[數字,...]},\"economy\":{\"E-1\":[...]},\"environment\":{\"E-1-1\":[...]}}。"
)


def _unwrap(data) -> dict:
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _indicators_from_template(data: dict) -> dict:
    out = {}
    for face in ("social", "economy", "environment"):
        out[face] = [
            {"id": it.get("id"), "title": it.get("title"), "inputs": it.get("inputs") or []}
            for it in (data.get(face) or []) if it.get("id")
        ]
    return out


def _indicators_from_sroi(data: dict) -> dict:
    out = {}
    for face, key in (("social", "sroi_social"), ("economy", "sroi_economy"), ("environment", "sroi_environment")):
        items = []
        for it in (data.get(key) or []):
            head = (it.get("head") or [""])[0]
            iid = head.split(".")[0].strip() if head else ""
            keys = it.get("key") or []
            inputs = []
            for k in keys:
                if k in ("價值計算", "評估標準"):
                    break
                if k:
                    inputs.append(k)
            if iid:
                items.append({"id": iid, "inputs": inputs})
        out[face] = items
    return out


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


async def _estimate(ctx: ModuleContext, payload: dict) -> dict:
    project_info = payload.get("project_info") or {}
    uuid = payload.get("uuid") or ""
    if not uuid:
        return result(False, "缺少要寫的專案 uuid", error="missing uuid")

    tmpl = await ctx.data.query(
        QuerySpec(tool="get_sroi_template", args={"uuid_project": uuid}, timeout=30.0)
    )
    if tmpl.status == "ok":
        indicators = _indicators_from_template(_unwrap(tmpl.data))
    else:
        legacy = await ctx.data.query(
            QuerySpec(tool="get_sroi", args={"uuid_project": uuid}, timeout=120.0)
        )
        if legacy.status != "ok":
            return result(False, f"（拿不到 SROI 指標表：{tmpl.reason or legacy.reason}）")
        indicators = _indicators_from_sroi(_unwrap(legacy.data))

    llm = ctx.llm
    if llm is None:
        return result(False, "此環境未注入 LLM，無法估 SROI", error="no llm")
    resp = await llm.ainvoke([
        SystemMessage(content=_SROI_PROMPT),
        HumanMessage(content=json.dumps({"project": project_info, "indicators": indicators}, ensure_ascii=False)),
    ])
    vals = _parse_json_obj(getattr(resp, "content", "") or "")
    payload_save = {"uuid_project": uuid}
    n = 0
    for face in ("social", "economy", "environment"):
        block = vals.get(face) or {}
        if isinstance(block, dict) and block:
            payload_save[face] = block
            n += len(block)
    if n == 0:
        return result(False, "（這個專案的描述還不足以估出 SROI 指標，補一點細節再試。）")

    saved = await ctx.data.query(
        QuerySpec(tool="save_sroi", args=payload_save, confirmed=True, timeout=120.0, encoding="json")
    )
    if saved.status != "ok":
        return result(False, f"（SROI 儲存失敗：{saved.reason}）")
    total = sum(len(indicators.get(f) or []) for f in ("social", "economy", "environment"))
    return result(
        True,
        (
            f"我依你的計畫內容，幫這個專案的 SROI 表**先填了 {n} 個指標的估計數字**"
            f"（整份共 {total} 個指標，其餘我沒把握、先留白給你）。\n\n"
            "⚠️ 這些是 **AI 依描述猜的草稿、不是真實數據** —— 請到專案頁面的"
            "「**成果展現 → SROI**」區，核對並把數字改成真的（改完 SROI 比率會自動重算）。"
        ),
        {"filled": n, "total": total},
    )


async def handle(ctx: ModuleContext, payload: dict) -> dict:
    action = ctx.action or "estimate"
    if action == "estimate":
        return await _estimate(ctx, payload)
    return result(False, f"未支援的 sustainability.sroi action：{action}")