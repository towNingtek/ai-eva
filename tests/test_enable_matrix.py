"""#127 enable matrix — 純函式單元測試（不碰 DB / Chainlit）。

覆蓋 (a) 卡的判準：
✅ 停用清單生效：menu 過濾、dispatch guard 擋下未啟用 app（core 例外）
✅ 缺省=None（未設 enabled_apps）→ 全開，行為不變
🟡 真實停用案例（sechome/yunlin 停 web_search 前後對照）需在 run 環境驗證（見卡片）
"""
import pytest

from app.apps._registry import (
    CORE_PROJECT,
    DEFAULT_PROJECT,
    App,
    filter_enabled,
    is_enabled_for,
)


def _app(app_id: str, project: str = DEFAULT_PROJECT) -> App:
    return App({"id": app_id, "project": project}, handle=lambda payload, msg: NotImplemented)


def _apps() -> list[App]:
    return [
        _app("hello_world"),
        _app("plain_chat"),
        _app("web_search"),
        _app("chat_analysis", project="sechome"),
    ]


class TestFilterEnabled:
    def test_none_means_all_on(self):
        app = _apps()
        assert filter_enabled(app, None) == app

    def test_empty_set_means_none_of_own(self):
        # enabled=空 set → 剩 core 的
        got = filter_enabled(_apps(), set())
        assert all(a.project == CORE_PROJECT for a in got)

    def test_allow_by_plain_id(self):
        got = {a.id for a in filter_enabled(_apps(), {"web_search"})}
        assert "web_search" in got
        assert "hello_world" not in got

    def test_allow_by_full_id(self):
        got = {a.id for a in filter_enabled(_apps(), {"sechome.chat_analysis"})}
        assert "chat_analysis" in got

    def test_core_always_visible_even_when_not_listed(self):
        apps = [_app("corething", project=CORE_PROJECT), _app("own", project="sechome")]
        got = {a.id for a in filter_enabled(apps, {"something_else"})}
        assert "corething" in got
        assert "own" not in got


class TestIsEnabledFor:
    def test_default_project_enabled_without_matrix(self):
        a = _app("web_search")
        assert is_enabled_for(a, DEFAULT_PROJECT, None) is True

    def test_blocked_when_not_in_matrix(self):
        a = _app("web_search")
        assert is_enabled_for(a, DEFAULT_PROJECT, {"hello_world"}) is False

    def test_core_always_enabled(self):
        a = _app("any", project=CORE_PROJECT)
        assert is_enabled_for(a, "sechome", set()) is True

    def test_full_id_in_matrix(self):
        a = _app("web_search", project="sechome")
        assert is_enabled_for(a, "sechome", {"sechome.web_search"}) is True

    def test_dispatch_guard_uses_this(self):
        # main.py 的 dispatch guard 就是 is_enabled_for；未啟用 → 擋下
        a = _app("web_search")
        blocked = not is_enabled_for(a, "yunlin", {"hello_world"})
        assert blocked is True