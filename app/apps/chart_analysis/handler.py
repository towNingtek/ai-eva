"""chart_analysis app — 把 sechome.chart module 串進 Chainlit 工具選單（#128 落地案例）。

薄 app：只負責把「登入者的資料後端」組好（SSO → CMSDataSource；無 SSO → StubDataSource，
方便未登入時也能看格式範例），實際 query 邏輯全在 module（跨後端共用）。

前端匯出（RD 版）：進入頁面渲染 ChartAnalysis CustomElement，SDG 長條圖 + PDF/PNG 匯出；
其 chart_query / chart_export 是 main.py 的 action callback（讀 cl.user_session["chart_element"]）。
"""
import logging
from datetime import date

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


def _element() -> cl.CustomElement:
    """ChartAnalysis 前端元件（RD 匯出依賴 chart_element 存 session）。"""
    element = cl.CustomElement(
        name="ChartAnalysis",
        display="inline",
        props={
            "year": str(date.today().year),
            "district": "",
            "sdgs": ["sdg9", "sdg12"],
            "items": [],
            "totalBudget": 0,
            "totalProjects": 0,
            "loading": False,
            "error": "",
        },
    )
    cl.user_session.set("chart_element", element)
    return element


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


async def _chart_source(project: str | None):
    """依登入者決定資料後端：SSO（CMS）→ CMSDataSource；否則 stub 示範。"""
    if project:
        runtime = cl.user_session.get("cms_runtime")
        if runtime:
            return CMSDataSource(runtime)
        return CMSDataSource(await _mock_runtime())
    return StubDataSource(_STUB_CHART)


async def handle(payload: str, msg: cl.Message) -> None:
    if not payload.strip():
        # 無快取資料時的初始畫面：渲染前端元件（RD 匯出 + SDG 圖表互動）。
        element = _element()
        await cl.Message(
            content="📊 請設定條件後生成 SDG 投入圖表，或匯出成 PDF / PNG。數值來自 CMS 專案資料。",
            elements=[element],
            parent_id=getattr(msg, "id", None),
        ).send()
        return

    try:
        user = cl.user_session.get("user")
        project = (getattr(user, "metadata", None) or {}).get("project") if user else None
        data = await _chart_source(project)

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