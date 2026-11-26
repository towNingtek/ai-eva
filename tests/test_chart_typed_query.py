"""雲林教育訓練 2026-11-26：圖表分析「打字查詢」一律「查詢失敗」。

原因：打字路徑呼叫 dashboard_chart_query，CMS manifest 只有 dashboard_sdg_data（面板按鈕用的）。
既有測試用假 runtime 認同一個假名字，所以一直沒抓到。這裡用 CMS 真實回應形狀測。
"""
import asyncio
from types import SimpleNamespace
from unittest import mock

from app.apps.chart_analysis import handler as h

CMS_REPLY = {"success": True, "data": {"year": "2025", "district": "", "budgetValues": [
    {"id": "sdg1", "value": 0, "count": 0}, {"id": "sdg4", "value": 5000000, "count": 1},
    {"id": "sdg11", "value": 5000000, "count": 1}], "totalBudget": 10000000, "totalProjects": 2}}


class FakeRuntime:
    """只認 CMS manifest 真的有的工具，其他一律 denied（同正式 ToolRuntime）。"""
    def __init__(self):
        self.calls = []

    async def execute(self, name, args, *, confirmed=False, timeout=None, encoding=None):
        self.calls.append((name, args))
        if name != "dashboard_sdg_data":
            return {"status": "denied", "reason": f"tool '{name}' not in manifest"}
        return {"status": "ok", "result": CMS_REPLY}


def _run(text):
    rt, sent = FakeRuntime(), []

    class Msg:
        def __init__(self, content="", **kw):
            self.content = content
        async def send(self):
            sent.append(self.content)

    session = {"user": SimpleNamespace(metadata={"project": "yunlin"}), "cms_runtime": rt}
    with mock.patch.object(h.cl, "user_session", mock.Mock(get=lambda k, d=None: session.get(k, d))), \
         mock.patch.object(h.cl, "Message", Msg):
        asyncio.run(h.handle(text, SimpleNamespace(id="m1")))
    return rt, sent


def test_typed_query_uses_the_cms_tool_and_succeeds():
    rt, sent = _run("2025 斗六市")
    assert [c[0] for c in rt.calls] == ["dashboard_sdg_data"]
    args = rt.calls[0][1]
    assert args["year"] == "2025" and args["district"] == "斗六市"
    assert len(args["sdgs"]) == 17
    assert "查詢失敗" not in sent[-1], sent
    assert "SDG4：1 件，NT$ 5,000,000" in sent[-1] and "共 2 件" in sent[-1]
    assert "SDG1：" not in sent[-1]  # 0 件不列（SDG11 不算）


def test_year_only_and_no_year_default():
    rt, sent = _run("2024")
    assert rt.calls[0][1]["district"] == "" and rt.calls[0][1]["year"] == "2024"
    rt, sent = _run("斗六市")
    assert rt.calls[0][1]["year"].isdigit()
