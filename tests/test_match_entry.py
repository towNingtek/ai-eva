"""媒合入口（ai-eva#237）：改名「尋找媒合夥伴」排第一、舊版「即將下線」排最後；
CMS 帶 /sso/handoff?open=<app_id>[&a=<uuid>] → eva_open cookie → 開場自動開啟並預選 A（只生效一次）。
"""
import asyncio
import importlib
import json
import re
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.apps import _registry
from app.apps.match_analysis import handler, task
from app.auth import issuers
from app.i18n import app_label
from app.surfaces import sso

# ── (a) 四語名稱 ────────────────────────────────────────────────

LABELS = {
    "match_analysis": {"zh": "尋找媒合夥伴", "en": "Find matching partners",
                       "ja": "マッチング相手を探す", "ko": "매칭 파트너 찾기"},
    "project_match": {"zh": "舊版媒合（即將下線）", "en": "Legacy matching (retiring)",
                      "ja": "旧マッチング（終了予定）", "ko": "이전 매칭(종료 예정)"},
}


@pytest.mark.parametrize("app_id", sorted(LABELS))
@pytest.mark.parametrize("lang", ["zh", "en", "ja", "ko"])
def test_app_label_four_languages(app_id, lang):
    assert app_label(app_id, lang=lang) == LABELS[app_id][lang]


def test_meta_badges():
    assert _registry.get_by_id("match_analysis").badge == "new"
    assert _registry.get_by_id("project_match").badge == "legacy"


# ── (b) 工具列順序 ──────────────────────────────────────────────

def test_toolbar_order_new_first_legacy_last():
    ids = [a.id for a in _registry.menu_apps()]
    assert ids[0] == "match_analysis"
    assert ids[-1] == "project_match"
    # 啟用矩陣過濾後順序不變
    enabled = set(ids)
    assert [a.id for a in _registry.filter_enabled(_registry.menu_apps(), enabled)
            ][0] == "match_analysis"


def test_toolbar_actions_carry_css_hook_ids(monkeypatch):
    """按鈕 DOM id＝eva-app-<app_id>-…（public/custom.css 靠它掛「新」徽章／弱化舊版）。"""
    from app import main
    a = _registry.get_by_id("match_analysis")
    assert main._action_id(a).startswith("eva-app-match_analysis-")
    css = open("public/custom.css", encoding="utf-8").read()
    assert 'button[id^="eva-app-match_analysis-"]::after' in css and 'content: "新"' in css
    assert re.search(r'button\[id\^="eva-app-project_match-"\]\s*\{[^}]*dashed', css)


# ── (c) handoff 帶 open／a → cookie；未註冊或沒權限 → 忽略 ─────────

ISSUER_ID = "tplanet-cms"
KID = "test-kid-237"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks():
    url = issuers.ISSUERS[ISSUER_ID]["jwks_url"]
    saved = issuers._JWKS_CACHE.get(url)
    issuers._JWKS_CACHE[url] = {"keys": {KID: _KEY.public_key()}, "exp": time.time() + 3600}
    yield
    if saved is None:
        issuers._JWKS_CACHE.pop(url, None)
    else:
        issuers._JWKS_CACHE[url] = saved


def _token() -> str:
    claims = {"iss": ISSUER_ID, "aud": "ai-eva", "exp": int(time.time()) + 300,
              "tenant_id": "nantou-gov", "user_id": 7, "email": "u@example.com"}
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": KID})


class _FakeConn:
    async def execute(self, *a):
        return "OK"

    async def close(self):
        pass


def _client(monkeypatch, manifest, enabled=None):
    mod = importlib.import_module("app.surfaces.sso")
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "test-secret-237-" + "x" * 32)

    async def _connect():
        return _FakeConn()

    async def _enabled(project):
        return enabled

    from app.projects import registry as project_registry
    monkeypatch.setattr(mod, "_DATABASE_URL", "postgresql://fake/db")
    monkeypatch.setattr(mod, "_connect", _connect)
    monkeypatch.setattr(mod.issuers, "fetch_manifest", lambda *a, **k: manifest)
    monkeypatch.setattr(project_registry, "get_enabled_apps", _enabled)
    from fastapi.testclient import TestClient
    return TestClient(mod.fastapi_app)


def _set_cookie(resp, name):
    for h in resp.headers.get_list("set-cookie"):
        if h.startswith(name + "="):
            return h
    return None


def _open_value(resp):
    raw = _set_cookie(resp, sso.OPEN_COOKIE)
    assert raw is not None
    m = re.match(r"eva_open=([^;]*)", raw)
    value = m.group(1)
    if not value or value == '""' or "Max-Age=0" in raw:
        return None
    if value.startswith('"'):
        value = json.loads(value)
    return json.loads(unquote(value))


UUID_A = "11111111-2222-3333-4444-555555555555"


def test_handoff_with_open_and_a_sets_cookie(monkeypatch, jwks):
    c = _client(monkeypatch, {"tools": []})
    resp = c.get("/sso/handoff", params={"token": _token(), "open": "match_analysis", "a": UUID_A},
                 follow_redirects=False)
    assert resp.status_code == 303
    raw = _set_cookie(resp, sso.OPEN_COOKIE)
    assert "HttpOnly" in raw and "Max-Age" in raw
    data = _open_value(resp)
    assert data["app"] == "match_analysis" and data["a"] == UUID_A and data["n"]


def test_handoff_html_interstitial_keeps_open_and_a(monkeypatch, jwks):
    c = _client(monkeypatch, {"tools": []})
    resp = c.get("/sso/handoff", params={"token": _token(), "open": "match_analysis", "a": UUID_A},
                 headers={"accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 200
    assert "open=match_analysis" in resp.text and UUID_A in resp.text


def test_handoff_without_open_clears_cookie(monkeypatch, jwks):
    c = _client(monkeypatch, {"tools": []})
    resp = c.get("/sso/handoff", params={"token": _token()}, follow_redirects=False)
    assert resp.status_code == 303
    assert _open_value(resp) is None


@pytest.mark.parametrize("open_id", ["no_such_app", "../etc", "<script>", "x" * 200])
def test_handoff_unknown_app_is_ignored(monkeypatch, jwks, open_id):
    c = _client(monkeypatch, {"tools": []})
    resp = c.get("/sso/handoff", params={"token": _token(), "open": open_id}, follow_redirects=False)
    assert resp.status_code == 303                     # 轉址照常
    assert _open_value(resp) is None


def test_handoff_role_denied_app_is_ignored(monkeypatch, jwks):
    c = _client(monkeypatch, {"tools": [], "apps": {"match_analysis": False}})
    resp = c.get("/sso/handoff", params={"token": _token(), "open": "match_analysis", "a": UUID_A},
                 follow_redirects=False)
    assert resp.status_code == 303
    assert _open_value(resp) is None


def test_handoff_app_not_enabled_for_project_is_ignored(monkeypatch, jwks):
    c = _client(monkeypatch, {"tools": []}, enabled={"project_match"})
    resp = c.get("/sso/handoff", params={"token": _token(), "open": "match_analysis"}, follow_redirects=False)
    assert _open_value(resp) is None


def test_resolve_open_rules():
    assert sso.resolve_open("match_analysis", UUID_A, {}, None) == {"app": "match_analysis", "a": UUID_A}
    assert sso.resolve_open("project_match", UUID_A, {}, None) == {"app": "project_match"}   # a 只給新版媒合
    assert sso.resolve_open("match_analysis", "bad uuid!", {}, None) == {"app": "match_analysis"}
    assert sso.resolve_open("no_such_app", None, {}, None) is None
    assert sso.resolve_open(None, None, {}, None) is None
    assert sso.resolve_open("match_analysis", None, {"apps": {"match_analysis": False}}, None) is None
    assert sso.resolve_open("match_analysis", None, {"apps": {"match_analysis": True}}, None) == {"app": "match_analysis"}


# ── (d) 開場讀 open → 開啟該工具；讀 a → 只在 A 可發起時預選 ──────────

def _cookie_header(intent):
    return f"other=1; {sso.OPEN_COOKIE}={sso.encode_open(intent)}"


def test_opening_reads_cookie_and_opens_that_app(monkeypatch):
    from app import main
    opened = []

    async def fake_open(app_id, preselect_a=None):
        opened.append((app_id, preselect_a))

    monkeypatch.setattr(main, "_open_app_by_id", fake_open)
    monkeypatch.setattr(main, "_session_cookie", lambda: _cookie_header({"app": "match_analysis", "a": UUID_A}))
    got = asyncio.run(main._auto_open_from_cookie())
    assert got == {"app": "match_analysis", "a": UUID_A}
    assert opened == [("match_analysis", UUID_A)]


def test_opening_without_cookie_opens_nothing(monkeypatch):
    from app import main
    opened = []

    async def fake_open(app_id, preselect_a=None):
        opened.append(app_id)

    monkeypatch.setattr(main, "_open_app_by_id", fake_open)
    monkeypatch.setattr(main, "_session_cookie", lambda: "foo=bar")
    assert asyncio.run(main._auto_open_from_cookie()) is None
    assert opened == []


def test_open_app_by_id_passes_preselect_only_to_match(monkeypatch):
    """_open_app_by_id 等同按工具鈕；預選 A 放進 session 給 match_analysis 的面板。"""
    from app import main
    store, handled = {}, []

    class Msg:
        def __init__(self, content="", **_):
            self.content = content

        async def send(self):
            return self

    async def guard(app):
        return True

    async def handle(app, text, anchor):
        handled.append((app.id, store.get(main.MATCH_PRESELECT_KEY)))

    monkeypatch.setattr(main.cl, "Message", Msg)
    monkeypatch.setattr(main.cl, "user_session", SimpleNamespace(set=store.__setitem__, get=store.get))
    monkeypatch.setattr(main, "_guard_app", guard)
    monkeypatch.setattr(main, "_handle_app", handle)
    asyncio.run(main._open_app_by_id("match_analysis", preselect_a=UUID_A))
    asyncio.run(main._open_app_by_id("project_match", preselect_a=UUID_A))
    assert handled == [("match_analysis", UUID_A), ("project_match", None)]
    assert main.MATCH_PRESELECT_KEY == task.PRESELECT_KEY


class CMS:
    """假 CMS（有 manifest）：mine＝我的案，initiable＝本站可發起。"""

    def __init__(self, mine, initiable):
        self.mine, self.initiable = list(mine), list(initiable)

    def is_allowed(self, name):
        return True

    async def execute(self, name, args, confirmed=False):
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": self.mine}}}
        if name == handler.INITIABLE_TOOL:
            items = [{"uuid": u, "name": f"本站 {u}"} for u in self.initiable]
            return {"status": "ok", "result": {"data": {"count": len(items), "items": items}}}
        return {"status": "ok", "result": {"data": {"name": f"專案 {args['uuid']}", "philosophy": ""}}}


@pytest.fixture
def tenv(monkeypatch, tmp_path):
    monkeypatch.setattr(task, "TASK_DIR", tmp_path)
    task._ACTIVE.clear()
    pushes = []

    async def acall(args):
        pushes.append(args)

    monkeypatch.setattr(task.cl, "CopilotFunction",
                        lambda name, args: SimpleNamespace(acall=lambda: acall(args)))
    path = task.scope_path({"issuer": "cms", "project": "dev", "user_id": 1}, "thread-237")
    return SimpleNamespace(path=path, pushes=pushes)


async def _settle(path):
    for _ in range(50):
        worker = task._ACTIVE.get(path)
        if worker is None:
            return
        await worker


def _open(tenv, cms, pre):
    async def go():
        await task.open_task(tenv.path, cms, preselect_a=pre)
        await _settle(tenv.path)
        return task._load(tenv.path)
    return asyncio.run(go())


def test_preselect_a_when_initiable(tenv):
    t = _open(tenv, CMS(mine=["x", "y"], initiable=["a1", "a2"]), "a2")
    assert t["status"] == "select"
    assert t["a"] == "a2"
    assert tenv.pushes[-1]["matchTask"]["a"] == "a2"      # 推給面板的快照帶 a → 面板預選


def test_preselect_ignored_when_not_initiable(tenv):
    t = _open(tenv, CMS(mine=["x", "y"], initiable=["a1", "a2"]), "x")   # 我的案，但本站不可發起
    assert t["status"] == "select"
    assert t["a"] is None


def test_preselect_applies_to_resumed_select_task(tenv):
    cms = CMS(mine=["x"], initiable=["a1", "a2"])
    assert _open(tenv, cms, None)["a"] is None
    assert _open(tenv, cms, "a1")["a"] == "a1"
    assert _open(tenv, cms, "zzz")["a"] == "a1"             # 不合格的 a 不覆蓋


def test_open_from_tool_takes_preselect_once(monkeypatch):
    store = {task.PRESELECT_KEY: UUID_A}
    monkeypatch.setattr(task, "_session_get", store.get)
    monkeypatch.setattr(task.cl, "user_session", SimpleNamespace(set=store.__setitem__, get=store.get))
    assert task.take_preselect() == UUID_A
    assert task.take_preselect() is None


# ── (e) open 只生效一次 ─────────────────────────────────────────

def test_open_cookie_consumed_only_once():
    header = _cookie_header({"app": "match_analysis", "a": UUID_A})
    assert sso.consume_open(header) == {"app": "match_analysis", "a": UUID_A}
    assert sso.consume_open(header) is None             # 同一 cookie 重整／重連不再開
    assert sso.consume_open(_cookie_header({"app": "match_analysis"})) == {"app": "match_analysis"}  # 新 handoff 新 nonce


def test_auto_open_runs_once_per_cookie(monkeypatch):
    from app import main
    opened = []

    async def fake_open(app_id, preselect_a=None):
        opened.append(app_id)

    header = _cookie_header({"app": "match_analysis"})
    monkeypatch.setattr(main, "_open_app_by_id", fake_open)
    monkeypatch.setattr(main, "_session_cookie", lambda: header)
    asyncio.run(main._auto_open_from_cookie())
    asyncio.run(main._auto_open_from_cookie())
    assert opened == ["match_analysis"]


def test_bad_cookie_values_ignored():
    for bad in ["", "eva_open=", "eva_open=%7Bnot-json", 'eva_open=%5B1%2C2%5D', "eva_open=%7B%22app%22%3A1%7D"]:
        assert sso.consume_open(bad) is None


# ── (f) 工具選單送出的標籤字＝點工具（不是回答） ─────────────────────

def test_tool_menu_label_opens_task_like_button(monkeypatch):
    """custom.js 把選單項目的標籤（各語言）當訊息送出；要和按鈕一樣開星球，不能掉進舊選案流程。"""
    from app.apps.match_analysis import handler
    opened, texts = [], []

    async def fake_open():
        opened.append(True)
        return True

    async def fake_on_text(text):
        texts.append(text)
        return True

    monkeypatch.setattr(task, "open_from_tool", fake_open)
    monkeypatch.setattr(task, "on_text", fake_on_text)
    for label in ("尋找媒合夥伴", "Find matching partners", "マッチング相手を探す", "매칭 파트너 찾기", ""):
        asyncio.run(handler.handle(label, None))
    assert len(opened) == 5 and texts == []
    asyncio.run(handler.handle("我們有竹編老師", None))      # 真正的回答照舊交給 on_text
    assert texts == ["我們有竹編老師"] and len(opened) == 5
