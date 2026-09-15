"""#128 adapter 等價 — 同一個 module 換資料後端，輸出結構一致。

判準 2（(b) 卡）：把 chart module 分別接在
a) 新的 CMSDataSource（背後是假的 ToolRuntime，模擬 CMS 的 {success,data} 信封）
b) StubDataSource（同一份資料）
兩者 query 應回傳結構一致的 AdapterResult（僅 provider 欄不同），
證實「換後端不改 module 邏輯」。
"""
import asyncio
from typing import cast

import pytest

from app.adapters.base import AdapterResult, QuerySpec
from app.adapters.registry import create, get_adapter_cls, register
from app.modules.registry import invoke
from app.modules.base import ModuleContext

_CHART_DATA = {
    "series": [{"year": 2025, "district": "竹山", "sdg": 9, "label": "創新生態", "amount": 120000}],
    "total": 120000,
    "buckets": ["2025"],
}


class _FakeRuntime:
    """假 ToolRuntime：直接回 CMS 風格 {success, data} 信封，模擬 manifest 允許。"""

    def __init__(self):
        self.called = []

    async def execute(self, name, args=None, *, confirmed=False, timeout=None, encoding=None):
        self.called.append((name, args))
        return {"status": "ok", "result": {"success": True, "data": _CHART_DATA}}


def test_providers_registered():
    assert get_adapter_cls("tplanet-cms") is not None
    assert get_adapter_cls("stub") is not None
    # 未註冊 provider → 是 None（防 typo 靜默 fallback）
    assert get_adapter_cls("no-such-provider") is None


async def _cms_result() -> AdapterResult:
    from app.adapters.cms import CMSDataSource
    from app.tools.runtime import ToolRuntime

    cms = CMSDataSource(cast(ToolRuntime, _FakeRuntime()))
    return await cms.query(QuerySpec(tool="dashboard_chart_query", args={"year": 2025}))


async def _stub_result() -> AdapterResult:
    from app.adapters.stub import StubDataSource

    stub = StubDataSource({"dashboard_chart_query": _CHART_DATA})
    return await stub.query(QuerySpec(tool="dashboard_chart_query", args={"year": 2025}))


async def test_cms_vs_stub_equivalent():
    cms = await _cms_result()
    stub = await _stub_result()
    assert cms.status == stub.status == "ok"
    assert cms.data == stub.data          # 剝信封後結構一致
    assert cms.provider != stub.provider  # 只差 provider 識別


async def test_module_same_on_both_backends():
    """把 chart module 接到兩個後端各跑一次 — 這是 (b) 卡判準 2 的本體。"""
    from app.adapters.cms import CMSDataSource
    from app.adapters.stub import StubDataSource
    from app.tools.runtime import ToolRuntime

    payload = {"year": 2025, "district": "竹山"}

    cms_ctx = ModuleContext(project="sechome", data=CMSDataSource(cast(ToolRuntime, _FakeRuntime())), action="query")
    cms_res = await invoke("sechome.chart", cms_ctx, payload)

    stub_ctx = ModuleContext(project="sechome", data=StubDataSource({"dashboard_chart_query": _CHART_DATA}), action="query")
    stub_res = await invoke("sechome.chart", stub_ctx, payload)

    assert cms_res["ok"] is stub_res["ok"] is True
    assert cms_res["data"]["data"] == stub_res["data"]["data"]  # 資料一致
    assert cms_res["data"]["provider"] != stub_res["data"]["provider"]


def test_unwrap_cms():
    from app.adapters.base import unwrap_cms

    assert unwrap_cms({"data": {"x": 1}}) == {"x": 1}
    assert unwrap_cms({"success": True, "data": {"x": 2}}) == {"x": 2}   # 剝信封
    assert unwrap_cms([1, 2]) == [1, 2]                                  # 非 dict → 原樣
    assert unwrap_cms("plain") == "plain"


def test_custom_provider_registration():
    """註冊一個第三方 provider → create() 回它（泛型 open 的證明）。"""
    from app.adapters.base import DataSource

    class ThirdParty(DataSource):
        provider = "third-party"

        def __init__(self, *a, **k):
            self.prefix = "tp"

        async def query(self, spec):
            return AdapterResult(status="ok", provider=self.provider, data={"echo": spec.tool})

    register("third-party", ThirdParty)
    inst = create("third-party")
    assert inst is not None
    assert inst.provider == "third-party"
    assert get_adapter_cls("third-party") is ThirdParty