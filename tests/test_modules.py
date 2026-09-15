"""#129 module 契約 — module 註冊／context 注入／啟用矩陣，SDG 流程經 stub adapter 可測。

判準（(c) 卡）：
✅ 換 SDG module 的資料後端（stub ↔ CMS）→ 邏輯零修改，僅 adapter 換檔
✅ LLM / uuid「注入」而非 module 自取
✅ enabled_modules 過濾（同 apps 模式）
🟡 真實 CMS 端到端（manifest→execute）需 run 環境驗證
"""
import pytest

from app.adapters.stub import StubDataSource
from app.modules.base import ModuleContext, result
from app.modules.registry import (
    CORE_PROJECT,
    discover,
    get_by_id,
    invoke,
    modules_for_project,
)


class FakeLLM:
    """假 LLM：回給定的 content。/ langchain-callable 形狀：resp.content 字串。"""

    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, messages):
        return _Resp(self._content)


class _Resp:
    def __init__(self, content: str):
        self.content = content


def test_registry_discovers_core_modules():
    mods = discover()
    # (b) 首例 + (c) 三模組都在
    for m in ("sechome.chart", "sustainability.sdg", "sustainability.sroi", "sechome.project-management"):
        assert m in mods, f"{m} 未註冊"


def test_module_meta_contract():
    for mid, mod in discover().items():
        assert mod.id == mid
        assert mod.project
        assert isinstance(mod.actions, list)


def test_sdg_meta_actions():
    sdg = get_by_id("sustainability.sdg")
    assert sdg is not None
    assert sdg.actions == ["generate"]


def test_modules_for_project_multi_tenant():
    all_mods = modules_for_project("sechome", enabled=None)
    # sechome 自己的 + core 的都會算
    ids = {m.id for m in all_mods}
    assert "sustainability.sdg" in ids
    assert "sustainability.sroi" in ids

    # enabled_modules 過濾（#129）：enabled=set() → 只留 core 常駐
    only_core = modules_for_project("sechome", enabled=set())
    assert all(m.project == CORE_PROJECT for m in only_core)
    assert "sustainability.sdg" not in {m.id for m in only_core}  # 非 core、不在 enabled

    # 另一 tenant（yunlin）沒有 sechome 自家 module
    yunlin_mods = modules_for_project("yunlin", enabled=None)
    assert "sustainability.sdg" not in {m.id for m in yunlin_mods}
    assert any(m.project == CORE_PROJECT for m in yunlin_mods)


async def test_sdg_module_runs_via_stub_adapter():
    """SDG module：stub adapter + 注入 LLM/uuid → 流程可跑（寫入 save_sdg 走 stub）。"""
    stub = StubDataSource({"save_sdg": {"saved": True}})
    sdg = get_by_id("sustainability.sdg")
    assert sdg is not None

    ctx = ModuleContext(
        project="sechome",
        data=stub,
        action="generate",
        make_llm=lambda api_key=None, user=None, streaming=False: FakeLLM(
            '{"9":"強化城鎮韌性基建","12":"推動永續消費"}'
        ),
    )
    res = await invoke("sustainability.sdg", ctx, {
        "project_info": {"name": "竹山小鎮"},
        "uuid": "proj-abc-123",
    })
    assert res["ok"] is True
    assert "SDG 9" in res["reply"] and "SDG 12" in res["reply"]
    # save_sdg 真的有送 tool + uuid（module 不寫死 uuid）
    assert any(c.tool == "save_sdg" and c.args.get("uuid") == "proj-abc-123" for c in stub.calls)


async def test_sdg_module_missing_uuid_is_injected_error():
    """module 不自己抓 uuid — 沒注入就報錯，證明「注入式」契約。"""
    stub = StubDataSource({})
    ctx = ModuleContext(project="sechome", data=stub, action="generate")
    res = await invoke("sustainability.sdg", ctx, {"project_info": {"name": "X"}})
    assert res["ok"] is False
    assert "uuid" in res.get("error", "")


async def test_invoke_unknown_module_or_action():
    stub = StubDataSource({})
    ctx = ModuleContext(project="sechome", data=stub, action="query")
    res = await invoke("not.a.module", ctx, {})
    assert res["ok"] is False
    res = await invoke("sustainability.sdg", ctx, {})  # sdg 不支援 query action
    assert res["ok"] is False


def test_module_result_shape():
    r = result(True, "done", {"k": 1})
    assert set(r) == {"ok", "reply", "data", "error"}
    assert r["ok"] is True and r["data"] == {"k": 1} and r["error"] == ""