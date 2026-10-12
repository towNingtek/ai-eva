"""#308 角色層開關 — 一般使用者不可用法規檢核（純函式，不碰 DB / Chainlit）。

CMS manifest 帶 `apps: {app_id: bool}`；AI-Eva 依此濾選單、擋 dispatch。
"""
from app.apps._registry import App, filter_role, role_allows


def _app(app_id: str) -> App:
    return App({"id": app_id, "project": "yunlin"}, handle=lambda payload, msg: NotImplemented)


REG = _app("regulation_check")
MATCH = _app("project_match")


class TestRoleAllows:
    def test_member_denied_regulation_check(self):
        assert role_allows(REG, {"regulation_check": False}) is False

    def test_admin_allowed_regulation_check(self):
        assert role_allows(REG, {"regulation_check": True}) is True

    def test_unlisted_app_not_gated(self):
        # CMS 只列有角色限制的 app；專案媒合不在清單 → 照常可用
        assert role_allows(MATCH, {"regulation_check": False}) is True

    def test_no_manifest_apps_means_no_restriction(self):
        # 非 SSO、或舊版 CMS 沒帶 apps → 行為等同現狀
        assert role_allows(REG, None) is True
        assert role_allows(REG, {}) is True

    def test_non_bool_value_denied(self):
        # CMS 說了算：值不是 True 就不放行（"false"、None 都擋）
        assert role_allows(REG, {"regulation_check": "false"}) is False
        assert role_allows(REG, {"regulation_check": None}) is False


class TestFilterRole:
    def test_member_menu_hides_regulation_check(self):
        got = [a.id for a in filter_role([REG, MATCH], {"regulation_check": False})]
        assert got == ["project_match"]

    def test_admin_menu_keeps_both(self):
        got = [a.id for a in filter_role([REG, MATCH], {"regulation_check": True})]
        assert got == ["regulation_check", "project_match"]
