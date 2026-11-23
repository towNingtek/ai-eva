"""#206：通行證語言 → SSO session / current_lang()；refresh 更新；4 語字串表無缺鍵。

用自簽 RS256 測試金鑰簽 handoff token，預先塞進 issuers 的 JWKS 快取（不打網路）；
PG 用假連線（記錄 INSERT/UPDATE 參數）。
"""
import asyncio
import importlib
import json
import pathlib
import re
import string
import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import i18n
from app.auth import issuers
from app.i18n import strings as i18n_strings

ISSUER_ID = "tplanet-cms"
KID = "test-kid-206"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _jwks_cache():
    url = issuers.ISSUERS[ISSUER_ID]["jwks_url"]
    saved = issuers._JWKS_CACHE.get(url)
    issuers._JWKS_CACHE[url] = {"keys": {KID: _KEY.public_key()}, "exp": time.time() + 3600}
    yield
    if saved is None:
        issuers._JWKS_CACHE.pop(url, None)
    else:
        issuers._JWKS_CACHE[url] = saved


def _token(lang=..., **extra) -> str:
    claims = {
        "iss": ISSUER_ID, "aud": "ai-eva", "exp": int(time.time()) + 300,
        "tenant_id": "nantou-gov", "user_id": 7, "email": "u@example.com",
    }
    if lang is not ...:
        claims["lang"] = lang
    claims.update(extra)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": KID})


# ── 假 Chainlit user_session（current_lang() 讀它）──────────────────
class _FakeUserSession(dict):
    def set(self, k, v):
        self[k] = v


@pytest.fixture
def user_session():
    import chainlit as cl

    fake = _FakeUserSession()
    with patch.object(cl, "user_session", fake):
        yield fake


# ── 假 PG ──────────────────────────────────────────────────────────
class _FakeConn:
    def __init__(self, store):
        self.store = store

    async def execute(self, sql, *args):
        self.store["executed"].append((sql, args))
        if sql.startswith("INSERT INTO sso_sessions"):
            sid, identity, manifest, refresh_token = args[:4]
            self.store["rows"][sid] = {
                "identity": json.loads(identity), "manifest": json.loads(manifest),
                "refresh_token": refresh_token, "expired": False,
            }
        elif sql.startswith("UPDATE sso_sessions") and "identity" in sql:
            sid, manifest, refresh_token, _ttl, identity = args
            row = self.store["rows"][sid]
            row.update(manifest=json.loads(manifest), refresh_token=refresh_token,
                       identity=json.loads(identity))
        return "OK"

    async def fetchrow(self, sql, *args):
        row = self.store["rows"].get(args[0])
        return dict(row) if row else None

    async def close(self):
        pass


@pytest.fixture
def sso():
    mod = importlib.import_module("app.surfaces.sso")
    store = {"rows": {}, "executed": []}

    async def _connect():
        return _FakeConn(store)

    with patch.object(mod, "_DATABASE_URL", "postgresql://fake/db"), \
         patch.object(mod, "_connect", _connect), \
         patch.object(mod.issuers, "fetch_manifest", return_value={"tools": []}):
        yield mod, store


# ── (a) ja → session 與 current_lang() 都是 ja ─────────────────────
def test_ja_token_sets_identity_session_and_current_lang(sso, user_session):
    mod, store = sso
    assert issuers.verify_handoff(_token("ja"))["lang"] == "ja"

    sess = asyncio.run(mod.establish_sso_session(_token("ja"), "rt-1"))
    assert sess["identity"]["lang"] == "ja"
    # 存進 durable session（INSERT 的 identity）
    assert store["rows"][sess["session_id"]]["identity"]["lang"] == "ja"
    got = asyncio.run(mod.get_sso_session(sess["session_id"]))
    assert got["identity"]["lang"] == "ja"

    # 載入到連線 → current_lang()
    assert i18n.set_current_lang(got["identity"]["lang"]) == "ja"
    assert user_session["lang"] == "ja"
    assert i18n.current_lang() == "ja"
    assert i18n.t("btn.confirm") == i18n_strings.STRINGS["btn.confirm"]["ja"]
    assert i18n.chainlit_locale(i18n.current_lang()) == "ja"


def test_current_lang_falls_back_to_user_metadata(user_session):
    class _User:
        metadata = {"lang": "ko"}

    user_session["user"] = _User()
    assert i18n.current_lang() == "ko"


def test_handoff_sets_user_metadata_and_lang_cookie(sso, monkeypatch):
    mod, _ = sso
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "test-secret-206-" + "x" * 32)
    from fastapi.testclient import TestClient

    client = TestClient(mod.fastapi_app)
    resp = client.get("/sso/handoff", params={"token": _token("ja")}, follow_redirects=False)
    assert resp.status_code == 303
    assert "eva_lang=ja" in resp.headers.get("set-cookie", "")
    access = re.search(r"access_token=([^;]+)", resp.headers.get("set-cookie", ""))
    assert access, resp.headers.get("set-cookie")
    claims = jwt.decode(access.group(1).strip('"'), options={"verify_signature": False})
    assert claims["metadata"]["lang"] == "ja"


# ── (b) 缺少／不合法 → zh ───────────────────────────────────────────
@pytest.mark.parametrize("bad", [..., None, "", "fr", "zh-TW", "JA-jp", 123, ["ja"], "<script>"])
def test_missing_or_invalid_lang_is_zh(bad, sso, user_session):
    mod, store = sso
    idn = issuers.verify_handoff(_token(bad))
    assert idn["lang"] == "zh"
    sess = asyncio.run(mod.establish_sso_session(_token(bad)))
    assert store["rows"][sess["session_id"]]["identity"]["lang"] == "zh"
    assert i18n.set_current_lang(idn["lang"]) == "zh"
    assert i18n.current_lang() == "zh"


def test_case_and_whitespace_are_normalized():
    assert issuers.verify_handoff(_token(" KO "))["lang"] == "ko"
    for v in ("zh", "en", "ja", "ko"):
        assert i18n.normalize_lang(v) == v


def test_current_lang_outside_chainlit_context_is_zh():
    assert i18n.current_lang() == "zh"
    assert i18n.t("btn.cancel") == i18n_strings.STRINGS["btn.cancel"]["zh"]


# ── (c) refresh 後語言更新 ─────────────────────────────────────────
def test_refresh_updates_lang(sso, user_session):
    mod, store = sso
    sess = asyncio.run(mod.establish_sso_session(_token("ja"), "rt-1"))
    sid = sess["session_id"]

    with patch.object(mod.issuers, "refresh_manifest",
                      return_value={"tools": [], "refresh_token": "rt-2", "lang": "ko"}):
        out = asyncio.run(mod.refresh_sso_session(sid))
    assert out["identity"]["lang"] == "ko"
    assert store["rows"][sid]["identity"]["lang"] == "ko"            # 持久化
    assert asyncio.run(mod.get_sso_session(sid))["identity"]["lang"] == "ko"
    i18n.set_current_lang(out["identity"]["lang"])
    assert i18n.current_lang() == "ko"


def test_refresh_with_new_handoff_token_updates_lang(sso):
    mod, store = sso
    sid = asyncio.run(mod.establish_sso_session(_token("zh"), "rt-1"))["session_id"]
    with patch.object(mod.issuers, "refresh_manifest",
                      return_value={"tools": [], "token": _token("en")}):
        out = asyncio.run(mod.refresh_sso_session(sid))
    assert out["identity"]["lang"] == "en"
    assert store["rows"][sid]["identity"]["lang"] == "en"


def test_refresh_invalid_lang_is_zh_and_missing_keeps_current(sso):
    mod, store = sso
    sid = asyncio.run(mod.establish_sso_session(_token("ja"), "rt-1"))["session_id"]
    with patch.object(mod.issuers, "refresh_manifest", return_value={"tools": []}):
        out = asyncio.run(mod.refresh_sso_session(sid))
    assert out["identity"]["lang"] == "ja"           # 回應沒提語言 → 沿用
    with patch.object(mod.issuers, "refresh_manifest", return_value={"tools": [], "lang": "fr"}):
        out = asyncio.run(mod.refresh_sso_session(sid))
    assert out["identity"]["lang"] == "zh"           # 不合法 → zh
    assert store["rows"][sid]["identity"]["lang"] == "zh"


def test_refresh_degraded_keeps_lang(sso):
    mod, _ = sso
    sid = asyncio.run(mod.establish_sso_session(_token("ko"), "rt-1"))["session_id"]
    with patch.object(mod.issuers, "refresh_manifest", side_effect=RuntimeError("401")):
        out = asyncio.run(mod.refresh_sso_session(sid))
    assert out.get("degraded") and out["identity"]["lang"] == "ko"


# ── (d) 4 語字串表無缺鍵 ───────────────────────────────────────────
def _fields(s: str) -> set:
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def _assert_complete(table: dict, keys):
    for key in keys:
        entry = table[key]
        assert set(entry) == set(i18n.SUPPORTED_LANGS), f"{key}: {sorted(entry)}"
        ph = _fields(entry["zh"])
        for lang in i18n.SUPPORTED_LANGS:
            text = entry[lang]
            assert isinstance(text, str) and text.strip(), f"{key}[{lang}] empty"
            assert _fields(text) == ph, f"{key}[{lang}] placeholders {_fields(text)} != {ph}"


def test_supported_langs():
    assert i18n.SUPPORTED_LANGS == ("zh", "en", "ja", "ko")
    assert set(i18n.CHAINLIT_LOCALES) == set(i18n.SUPPORTED_LANGS)
    tr = pathlib.Path(__file__).resolve().parents[1] / ".chainlit" / "translations"
    for loc in i18n.CHAINLIT_LOCALES.values():
        assert (tr / f"{loc}.json").exists(), loc


def test_all_strings_have_all_four_languages():
    _assert_complete(i18n_strings.STRINGS, i18n_strings.STRINGS)
    _assert_complete(i18n_strings.APP_LABELS, i18n_strings.APP_LABELS)


def test_welcome_and_button_strings_complete():
    assert set(i18n_strings.WELCOME_KEYS) >= {"welcome.sso", "welcome.guest"}
    assert i18n_strings.BUTTON_KEYS
    _assert_complete(i18n_strings.STRINGS, i18n_strings.WELCOME_KEYS)
    _assert_complete(i18n_strings.STRINGS, i18n_strings.BUTTON_KEYS)


def test_every_tool_button_has_a_label():
    from app.apps._registry import discover, menu_apps

    discover()
    ids = {a.id for a in menu_apps()}
    assert ids, "no apps discovered"
    missing = ids - set(i18n_strings.APP_LABELS)
    assert not missing, f"tool buttons without 4-language labels: {sorted(missing)}"
    for app_id in ids:
        labels = {i18n.app_label(app_id, lang=lang) for lang in i18n.SUPPORTED_LANGS}
        assert len(labels) >= 2 or app_id in labels  # 至少真的有翻譯（非全部同字）


def test_main_uses_string_keys_that_exist():
    src = (pathlib.Path(__file__).resolve().parents[1] / "app" / "main.py").read_text("utf-8")
    used = set(re.findall(r'\bt\(\s*"([a-z_]+\.[a-z_.]+)"', src))
    assert used, "main.py does not use i18n.t()"
    assert not (used - set(i18n_strings.STRINGS)), sorted(used - set(i18n_strings.STRINGS))


def test_t_falls_back_and_formats():
    assert i18n.t("no.such.key", lang="en") == "no.such.key"
    s = i18n.t("app.not_found", lang="en", app_id="x")
    assert "x" in s
    assert i18n.t("btn.confirm", lang="fr") == i18n_strings.STRINGS["btn.confirm"]["zh"]
