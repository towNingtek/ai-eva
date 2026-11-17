"""專案媒合 1.5（townway#66 規格 / #71）—— stub runtime 驗收，不碰 CMS / LLM / 瀏覽器。

1.5 驗收標準（townway#78 計畫）：
✅ 1 第一批 = 20 筆
✅ 2 「載入更多」帶出第 21–40 筆
✅ 3 逐筆呈現：第 1 筆在 20 筆抓完前就推到元件
✅ 4 選 N 個對象 → N 張媒合卡（且只用勾選的，不隨機混入）
✅ 5 CMS / 權限錯誤要講清楚並記 log，不誤報成「專案不足」（ai-eva#137）
✅ 6 「專案不足」只在真的少於 2 個專案時出現
"""
import asyncio
import logging

import pytest

from app.apps.project_match import handler as pm
from app.apps.project_match.meta import META

ASPECTS = ("共同目標", "合作模式", "綜效", "挑戰")


def _project(i: int) -> dict:
    return {
        "uuid": f"u{i:03d}",
        "name": f"專案{i:03d}",
        "period": "2026-01-01 ~ 2026-12-31",
        "budget": 500000,
        "hoster": f"協會{i}",
        "philosophy": f"<p>理念{i}</p>",
    }


def pool(n: int) -> list[dict]:
    return [_project(i) for i in range(1, n + 1)]


class StubRuntime:
    def __init__(self, projects, list_result=None, broken=()):
        self.projects = {p["uuid"]: p for p in projects}
        self.order = [p["uuid"] for p in projects]
        self.list_result = list_result
        self.broken = set(broken)
        self.calls: list[tuple[str, dict]] = []

    def count(self, tool: str) -> int:
        return sum(1 for name, _ in self.calls if name == tool)

    async def execute(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        if name == "list_my_projects":
            if self.list_result is not None:
                return self.list_result
            return {"status": "ok", "result": {"data": {"projects": list(self.order)}}}
        if name == "get_project_info":
            uuid = args.get("uuid")
            if uuid in self.broken:
                return {"status": "error", "reason": "forbidden"}
            if uuid in self.projects:
                return {"status": "ok", "result": {"data": self.projects[uuid]}}
        return {"status": "error", "result": {}}


class FakeChainlit:
    """handler 用到的介面：user_session、Message(elements=).send()、CustomElement.update()。"""

    def __init__(self, session: dict):
        self._session = dict(session)
        self.sent: list[str] = []
        self.snapshots: list[dict] = []  # 每次 element.update() 時的 props
        outer = self

        class Message:
            def __init__(self, content: str = "", elements=None, **kwargs):
                self.content = content

            async def send(self):
                outer.sent.append(self.content)
                return self

        class CustomElement:
            def __init__(self, name: str, display: str = "inline", props=None):
                self.name = name
                self.props = dict(props or {})

            async def update(self):
                outer.snapshots.append({**self.props, "options": list(self.props.get("options", []))})

        self.Message = Message
        self.CustomElement = CustomElement
        self.user_session = self

    def get(self, key, default=None):
        return self._session.get(key, default)

    def set(self, key, value):
        self._session[key] = value


class Action:
    def __init__(self, payload):
        self.payload = payload


@pytest.fixture
def env(monkeypatch):
    def _make(runtime):
        fake = FakeChainlit({"cms_runtime": runtime, "cms_history": []})
        llm: list[str] = []

        async def fake_run_copilot(_runtime, text, _history=None, **_kw):
            llm.append(text)
            return {"reply": "（媒合結果）"}

        monkeypatch.setattr(pm, "cl", fake)
        monkeypatch.setattr(pm, "run_copilot", fake_run_copilot)
        return fake, llm

    return _make


def open_panel(env, runtime):
    fake, llm = env(runtime)
    asyncio.run(pm.handle("", None))
    return fake, llm


def options(fake) -> list[str]:
    el = fake.get("match_element")
    return [o["uuid"] for o in el.props["options"]] if el else []


class TestRegistry:
    def test_discoverable(self):
        from app.apps._registry import discover

        assert "project_match" in discover()

    def test_label(self):
        from app.apps._registry import get_by_id

        app = get_by_id("project_match")
        assert (app.label, app.id) == ("專案媒合", "project_match")

    def test_meta_scope(self):
        assert META["project"] == "sechome"


class TestBatching:
    def test_first_batch_is_20(self, env):
        """判準 1"""
        rt = StubRuntime(pool(45))
        fake, _ = open_panel(env, rt)
        assert options(fake) == [f"u{i:03d}" for i in range(1, 21)]
        assert rt.count("get_project_info") == 20
        assert fake.get("match_element").props["total"] == 45

    def test_load_more_brings_21_to_40(self, env):
        """判準 2"""
        rt = StubRuntime(pool(45))
        fake, _ = open_panel(env, rt)
        asyncio.run(pm.match_more(Action({})))
        assert options(fake)[20:] == [f"u{i:03d}" for i in range(21, 41)]
        asyncio.run(pm.match_more(Action({})))
        assert len(options(fake)) == 45
        asyncio.run(pm.match_more(Action({})))  # 已到底 → 不再查
        assert rt.count("get_project_info") == 45

    def test_streams_one_by_one(self, env):
        """判準 3：第 1 筆在其餘 19 筆抓完前就已推到元件。"""
        rt = StubRuntime(pool(25))
        fake, _ = open_panel(env, rt)
        counts = [len(s["options"]) for s in fake.snapshots if s.get("loading")]
        assert 1 in counts and max(counts) == 20
        assert counts == sorted(counts)  # 只增不減
        first = next(s for s in fake.snapshots if s["options"])
        assert len(first["options"]) == 1 and first["loading"] is True

    def test_info_failures_are_skipped_and_reported(self, env, caplog):
        rt = StubRuntime(pool(5), broken={"u002"})
        with caplog.at_level(logging.WARNING):
            fake, _ = open_panel(env, rt)
        assert "u002" not in options(fake) and len(options(fake)) == 4
        assert "1 筆" in fake.get("match_element").props["error"]
        assert "u002" in caplog.text

    def test_unnamed_project_is_kept_not_failed(self, env):
        """舊站搬來的未命名專案（新北 11 筆）仍可選，不算讀取失敗。"""
        projects = pool(3)
        projects[1]["name"] = ""
        rt = StubRuntime(projects)
        fake, _ = open_panel(env, rt)
        el = fake.get("match_element")
        assert options(fake) == ["u001", "u002", "u003"]
        assert "u002" in el.props["options"][1]["name"]
        assert not el.props["error"]

    def test_load_more_keeps_selection(self, env):
        """「載入更多」後已選的我的專案／對象不能被清掉（element.update 會重掛元件）。"""
        rt = StubRuntime(pool(45))
        fake, _ = open_panel(env, rt)
        el = fake.get("match_element")
        assert el.props["pickerId"]
        asyncio.run(pm.match_more(Action({"mine": "u001", "partners": ["u002", "u003"], "open": True})))
        assert el.props["mine"] == "u001"
        assert el.props["partners"] == ["u002", "u003"]
        assert el.props["open"] is True
        assert all(s["mine"] == "u001" for s in fake.snapshots[-21:])


class TestRun:
    def test_n_selected_gives_n_cards(self, env):
        """判準 4：選 3 個對象 → 3 次 LLM、3 張卡，且只出現勾選的。"""
        rt = StubRuntime(pool(25))
        fake, llm = open_panel(env, rt)
        picked = ["u003", "u007", "u015"]
        asyncio.run(pm.match_run(Action({"mine": "u001", "partners": picked})))
        assert len(llm) == 3
        cards = [m for m in fake.sent if m.startswith("### 🤝")]
        assert len(cards) == 3
        for text, uuid in zip(llm, picked):
            names = {p["name"] for p in pool(25) if p["name"] in text}
            assert names == {"專案001", f"專案{uuid[1:]}"}  # 不隨機混入其他專案
            assert {a for a in ASPECTS if a in text} == set(ASPECTS)
            assert "<p>" not in text

    def test_mine_excluded_and_duplicates_dropped(self, env):
        rt = StubRuntime(pool(5))
        fake, llm = open_panel(env, rt)
        asyncio.run(pm.match_run(Action({"mine": "u001", "partners": ["u001", "u002", "u002"]})))
        assert len(llm) == 1

    def test_unloaded_partner_ignored(self, env):
        rt = StubRuntime(pool(25))
        fake, llm = open_panel(env, rt)
        asyncio.run(pm.match_run(Action({"mine": "u001", "partners": ["u022"]})))  # 第二批，未載入
        assert llm == []
        assert any("至少勾選一個" in m for m in fake.sent)

    def test_requires_selection(self, env):
        rt = StubRuntime(pool(5))
        fake, llm = open_panel(env, rt)
        asyncio.run(pm.match_run(Action({"mine": "", "partners": []})))
        assert llm == []

    def test_no_extra_info_fetch_when_running(self, env):
        rt = StubRuntime(pool(5))
        fake, _ = open_panel(env, rt)
        asyncio.run(pm.match_run(Action({"mine": "u001", "partners": ["u002"]})))
        assert rt.count("get_project_info") == 5
        assert rt.count("list_my_projects") == 1


class TestErrors:
    def test_cms_error_is_not_reported_as_insufficient(self, env, caplog):
        """判準 5（ai-eva#137）"""
        rt = StubRuntime([], list_result={"status": "error", "reason": "permission denied"})
        with caplog.at_level(logging.ERROR):
            fake, llm = open_panel(env, rt)
        assert llm == []
        assert not any("專案不足" in m for m in fake.sent)
        assert any("無法讀取專案清單" in m and "permission denied" in m for m in fake.sent)
        assert "取專案清單失敗" in caplog.text

    def test_runtime_exception_is_not_reported_as_insufficient(self, env):
        class Boom(StubRuntime):
            async def execute(self, name, args):
                raise ConnectionError("cms down")

        fake, _ = open_panel(env, Boom([]))
        assert not any("專案不足" in m for m in fake.sent)
        assert any("無法讀取專案清單" in m for m in fake.sent)

    def test_insufficient_only_when_one_project(self, env):
        """判準 6"""
        fake, llm = open_panel(env, StubRuntime(pool(1)))
        assert llm == [] and any("專案不足" in m for m in fake.sent)
        assert fake.get("match_element") is None

    def test_two_projects_opens_panel(self, env):
        fake, _ = open_panel(env, StubRuntime(pool(2)))
        assert not any("專案不足" in m for m in fake.sent)
        assert len(options(fake)) == 2

    def test_llm_failure_per_card(self, env, monkeypatch):
        rt = StubRuntime(pool(5))
        fake, _ = open_panel(env, rt)
        calls = []

        async def flaky(_rt, text, _h=None, **_kw):
            calls.append(text)
            if len(calls) == 1:
                raise TimeoutError()
            return {"reply": "ok"}

        monkeypatch.setattr(pm, "run_copilot", flaky)
        asyncio.run(pm.match_run(Action({"mine": "u001", "partners": ["u002", "u003"]})))
        assert any("媒合分析失敗（TimeoutError）" in m for m in fake.sent)
        assert sum(m.startswith("### 🤝") for m in fake.sent) == 1
        assert fake.get("match_element").props["running"] is False
