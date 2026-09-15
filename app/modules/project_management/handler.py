"""project-management module handler — copilot 建案流程的 module 化（#129）。

- list_projects：讀類，直接 query adapter（list_my_projects）。
- create_project：寫類，adapter 會依 needs_confirm 回 need_confirm，
  呼叫端（copilot / main）負責出確認 UI，這裡只回該 query 的原始結果、
  不做資料後端假設。

引導式問答（收集欄位）的原 prompt 留在 provider 端（見 copilot.COPILOT_SYSTEM），
module 只管理「後端動作」，不取代對話互動。
"""
from __future__ import annotations

from app.adapters.base import QuerySpec
from app.modules.base import ModuleContext, result


async def _list(ctx: ModuleContext, payload: dict) -> dict:
    res = await ctx.data.query(QuerySpec(tool="list_my_projects", args=payload.get("args") or {}))
    if res.status != "ok":
        return result(False, f"列專案失敗（{res.status}）：{res.reason or '無資料'}")
    return result(True, "已列出專案", {"provider": res.provider, "data": res.data})


async def _create(ctx: ModuleContext, payload: dict) -> dict:
    args = payload.get("args") or {}
    res = await ctx.data.query(
        QuerySpec(tool="create_project", args=args, confirmed=bool(payload.get("confirmed")))
    )
    if res.status == "need_confirm":
        name = args.get("name") or "（未命名）"
        return result(False, f"要建立專案「{name}」嗎？確認後我就送出。", {
            "pending": {"name": "create_project", "args": args},
        })
    if res.status != "ok":
        return result(False, f"（建立專案失敗：{res.reason}）")
    return result(True, "專案已建立", {"provider": res.provider, "data": res.data})


async def handle(ctx: ModuleContext, payload: dict) -> dict:
    action = ctx.action or "list_projects"
    if action == "list_projects":
        return await _list(ctx, payload)
    if action == "create_project":
        return await _create(ctx, payload)
    return result(False, f"未支援的 project-management action：{action}")