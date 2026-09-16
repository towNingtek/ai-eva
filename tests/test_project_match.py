"""#134 過渡版專案媒合 —— 以 stub runtime 驗收，不碰 CMS / LLM / Chainlit session。

對應 #134 判準：
✅ 5 送進 LLM 的 intent 恰好出現 2 個不同專案名稱（不是把整池倒進去）
✅ 6 四個分析面向齊全（共同目標 / 合作模式 / 綜效 / 挑戰）
✅ 7 專案不足 2 筆 → 明確訊息且不呼叫 LLM
✅ 8 get_project_info 呼叫次數 == 專案池大小（沒有舊版抽中後重抓那筆）
✅ 1/2 app registry 查得到 project_match / 標籤正確
"""
import asyncio

import pytest

from app.apps.project_match import handler as pm
from app.apps.project_match.meta import META


ASPECTS = ("共同目標", "合作模式", "綜效", "挑戰")


def _project(uuid: str, name: str) -> dict:
    return {
        "uuid": uuid,
        "name": name,
        "period": "2026-01-01 ~ 2026-12-31",
        "budget": 500000,
        "hoster": f"{name}協會",
        "philosophy": f"<p>{name}的計畫理念</p>",
    }


POOL = [_project("u1", "鄉村走讀"), _project("u2", "海線淨灘"), _project("u3", "城南共餐")]


class StubRuntime:
    def __init__(self, projects: list[dict]):
        self.projects = projects
        self.calls: list[tuple[str, dict]] = []

    def count(self, tool: str) -> int:
        return sum(1 for name, _ in self.calls if name == tool)

    async def execute(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": [p["uuid"] for p in self.projects]}}}
        if name == "get_project_info":
            found = next((p for p in self.projects if p["uuid"] == args.get("uuid")), None)
            if found:
                return {"status": "ok", "result": {"data": found}}
        return {"status": "error", "result": {}}


class FakeChainlit:
    """只提供 handler 用到的兩個介面：user_session 與 Message().send()。"""

    def __init__(self, session: dict):
        self._session = dict(session)
        self.sent: list[str] = []
        outer = self

        class Message:
            def __init__(self, content: str = "", **kwargs):
                self.content = content

            async def send(self):
                outer.sent.append(self.content)
                return self

        self.Message = Message
        self.user_session = self

    def get(self, key, default=None):
        return self._session.get(key, default)

    def set(self, key, value):
        self._session[key] = value


@pytest.fixture
def run_handler(monkeypatch):
    """跑一次 handle()，回 (runtime, fake_cl, llm_calls)。"""

    def _run(projects: list[dict]):
        runtime = StubRuntime(projects)
        fake_cl = FakeChainlit({"cms_runtime": runtime, "cms_history": []})
        llm_calls: list[str] = []

        async def fake_run_copilot(_runtime, user_text, _history=None, **_kwargs):
            llm_calls.append(user_text)
            return {"reply": "（媒合結果）"}

        monkeypatch.setattr(pm, "cl", fake_cl)
        monkeypatch.setattr(pm, "run_copilot", fake_run_copilot)
        asyncio.run(pm.handle("", None))
        return runtime, fake_cl, llm_calls

    return _run


class TestRegistry:
    def test_discoverable(self):
        from app.apps._registry import discover

        assert "project_match" in discover()

    def test_label(self):
        from app.apps._registry import get_by_id

        app = get_by_id("project_match")
        assert (app.label, app.id) == ("專案媒合", "project_match")

    def test_meta_is_transitional_scope(self):
        assert META["project"] == "sechome"


class TestIntent:
    def test_exactly_two_distinct_project_names(self, run_handler):
        """判準 5：整池 3 個，intent 只能出現其中 2 個不同名稱。"""
        _, _, llm_calls = run_handler(POOL)
        assert len(llm_calls) == 1
        intent = llm_calls[0]
        present = {p["name"] for p in POOL if p["name"] in intent}
        assert len(present) == 2

    def test_four_analysis_aspects(self, run_handler):
        """判準 6：四個面向全在，不是只寫一句『請媒合這兩個專案』。"""
        _, _, llm_calls = run_handler(POOL)
        assert {a for a in ASPECTS if a in llm_calls[0]} == set(ASPECTS)

    def test_carries_project_fields_not_just_names(self, run_handler):
        _, _, llm_calls = run_handler(POOL)
        intent = llm_calls[0]
        assert "執行期間" in intent and "預算" in intent and "計劃理念" in intent
        assert "<p>" not in intent  # CMS 富文字的 HTML tag 要洗掉

    def test_no_extra_project_info_fetch(self, run_handler):
        """判準 8：每個專案只查一次，沒有舊版抽中後重抓那筆。"""
        runtime, _, _ = run_handler(POOL)
        assert runtime.count("get_project_info") == len(POOL)
        assert runtime.count("list_my_projects") == 1


class TestGuards:
    def test_single_project_refuses_without_calling_llm(self, run_handler):
        """判準 7：不足兩個專案 → 明確訊息，且不打 LLM。"""
        _, fake_cl, llm_calls = run_handler(POOL[:1])
        assert llm_calls == []
        assert any("至少需要兩個專案" in m for m in fake_cl.sent)

    def test_empty_pool_refuses(self, run_handler):
        _, fake_cl, llm_calls = run_handler([])
        assert llm_calls == []
        assert any("至少需要兩個專案" in m for m in fake_cl.sent)

    def test_unnamed_projects_are_skipped(self, run_handler):
        pool = [POOL[0], {**POOL[1], "name": ""}]
        _, fake_cl, llm_calls = run_handler(pool)
        assert llm_calls == []
        assert any("至少需要兩個專案" in m for m in fake_cl.sent)


def test_pick_pair_returns_two_distinct():
    pair = pm.pick_pair(POOL)
    assert len({p["uuid"] for p in pair}) == 2
