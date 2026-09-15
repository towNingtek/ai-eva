"""chart_analysis app — 把 sechome.chart module 串進 Chainlit 工具選單（#128 落地案例）。

薄 app：只負責把「登入者的資料後端」組好（SSO → CMSDataSource；無 SSO → StubDataSource，
方便未登入時也能看格式範例），實際 query 邏輯全在 module（跨後端共用）。
"""
import logging

import chainlit as cl

from app.adapters.base import QuerySpec
from app.adapters.cms import CMSDataSource
from app.adapters.stub import StubDataSource
from app.modules.base import ModuleContext
from app.modules.registry import get_by_id, invoke

logger = logging.getLogger(__name__)

# 未登入（stub）時的示範資料 — 格式與 CMS dashboard_chart_query 相容
_STUB_CHART = {
    "dashboard_chart_query": {
        "series": [
            {"year": 2025, "district": "竹山", "sdg": 9, "label": "創新生態", "amount": 120000},
            {"year": 2025, "district": "竹山", "sdg": 12, "label": "永續消費", "amount": 85000},
        ],
        "total": 205000,
        "buckets": ["2025"],
    },
}


def _fmt(data) -> str:
    """把 module 回傳的 chart data 渲染成文字（無瀏覽器 ChartAnalysis.jsx 時的 fallback）。"""
    inner = data.get("data") or {}
    series = inner.get("series") or []
    if not series:
        return "⚠️ 沒有符合條件的圖表資料。"
    lines = [
        f"- {r.get('year')}｜{r.get('district')}｜SDG {r.get('sdg')}｜{r.get('label')}：$ {r.get('amount'):,}"
        for r in series
        if r.get("amount") is not None
    ]
    return "📊 圖表查詢結果（後端：{}）\n{}".format(data.get("provider"), "\n".join(lines))


async def _mock_runtime():
    """無 SSO 時組一個只回 stub 資料的假 ToolRuntime，證明同一 module 換後端不用改。"""
    from app.tools.runtime import ToolRuntime

    rt = ToolRuntime(manifest={"tools": []})

    async def _stub_execute(name, args, *, confirmed=False, timeout=None, encoding=None):
        if name != "dashboard_chart_query":
            return {"status": "denied", "reason": f"tool '{name}' not in manifest", "tool": name}
        return {"status": "ok", "result": {"success": True, "data": _STUB_CHART[name]}, "tool": name}

    rt.execute = _stub_execute  # type: ignore[method-assign]
    return rt


async def handle(payload: str, msg: cl.Message) -> None:
    if not payload.strip():
        await cl.Message(
            content="📊 **圖表查詢**\n\n輸入要查的年度/地區（例：`2025 竹山`）。"
        ).send()
        return

    try:
        # 依登入者決定後端：SSO（CMS）→ CMSDataSource；否則 stub 示範
        user = cl.user_session.get("user")
        project = (getattr(user, "metadata", None) or {}).get("project") if user else None
        if project:
            runtime = cl.user_session.get("cms_runtime")
            data = CMSDataSource(runtime) if runtime else None
            if data is None:
                data = CMSDataSource(await _mock_runtime())
        else:
            data = StubDataSource(_STUB_CHART)

        year, _, rest = payload.partition(" ")
        ctx = ModuleContext(project=project or "stub", data=data, action="query")
        req: dict = {"year": int(year) if year.strip().isdigit() else None}
        if rest.strip():
            req["district"] = rest.strip()
        res = await invoke("sechome.chart", ctx, req)
        if res.get("ok"):
            await cl.Message(content=_fmt(res), parent_id=msg.id).send()
        else:
            await cl.Message(content=f"⚠️ 圖表查詢失敗：{res.get('reply')}", parent_id=msg.id).send()
    except Exception as e:  # noqa: BLE001
        logger.exception("chart_analysis failed")
        await cl.Message(
            content=f"⚠️ 圖表查詢出錯（{type(e).__name__}）", parent_id=msg.id
        ).send()