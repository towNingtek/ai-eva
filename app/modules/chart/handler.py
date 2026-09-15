"""chart module handler — generic chart query（#84 / #128 首例落地）。

只認 `ctx.data.query(QuerySpec(tool=...))` 的標準結果，不知道後端是 CMS 還是 stub。
query 結果的「標準化」在 adapter 那層（unwrap_cms），module 只消費 AdapterResult。

驗證方式（(b) 卡判準）：同一個 query payload，分別接到 CMSDataSource 與
StubDataSource，module 輸出的 result 結構一致（僅 provider 欄不同）。
"""
from __future__ import annotations

from app.adapters.base import QuerySpec
from app.modules.base import ModuleContext, result

# 通用 chart query/result schema（#84）：module 宣告它吃的過濾條件。
# 後端 adapter 負責把 tool + 過濾映到實際端點（CMS dashboard_sdg_data / stub key）。
CHART_QUERY_TOOL = "dashboard_chart_query"


async def _run_query(ctx: ModuleContext, payload: dict) -> dict:
    """執行通用 chart query。payload: {year?, district?, sdgs?}（皆可選過濾）。"""
    spec = QuerySpec(
        tool=payload.get("tool") or CHART_QUERY_TOOL,
        args={
            "year": payload.get("year"),
            "district": payload.get("district"),
            "sdgs": payload.get("sdgs"),
        },
        timeout=payload.get("timeout"),
    )
    res = await ctx.data.query(spec)
    if res.status != "ok":
        return result(False, f"chart 查詢失敗（{res.status}）：{res.reason or '無資料'}")
    return result(True, "chart 查詢完成", {"provider": res.provider, "data": res.data})


async def handle(ctx: ModuleContext, payload: dict) -> dict:
    action = ctx.action or "query"
    if action == "query":
        return await _run_query(ctx, payload)
    return result(False, f"未支援的 chart action：{action}")