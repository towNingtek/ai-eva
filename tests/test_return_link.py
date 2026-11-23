"""通用「返回來源網站」（ai-eva#172，Second Home 測試回饋 6）。

AI-Eva 是獨立產品：不認得 CMS，只認 issuer。issuer 在 handoff token 帶 return_url／
return_label，AI-Eva 只接受 https 且 host 在該 issuer 登記的 return_hosts 內的網址。
"""
import importlib
import json
import re
import time
from unittest.mock import patch
from urllib.parse import unquote

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import issuers

ISSUER_ID = "tplanet-cms"
KID = "test-kid-172"
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


def _token(**extra) -> str:
    claims = {"iss": ISSUER_ID, "aud": "ai-eva", "exp": int(time.time()) + 300,
              "tenant_id": "nantou-gov", "user_id": 7, "email": "u@example.com"}
    claims.update(extra)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": KID})


# ── 驗證規則 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://nantou-gov.sechome.cc/backend/cms_agent",
    "https://dev.4impact.cc/",
    "https://yunlin-beta.4impact.cc/backend",
])
def test_registered_https_hosts_accepted(url):
    got = issuers.safe_return(ISSUER_ID, url, "南投縣計畫數位管理系統")
    assert got == {"url": url, "label": "南投縣計畫數位管理系統"}


@pytest.mark.parametrize("url", [
    "http://nantou-gov.sechome.cc/",            # 不是 https
    "https://evil.example.com/",                # 網域沒登記
    "https://sechome.cc.evil.com/",             # 假冒後綴
    "https://evilsechome.cc/",                  # 不是子網域
    "https://user:pw@dev.4impact.cc/",          # 帶帳密
    "javascript:alert(1)",
    "//nantou-gov.sechome.cc/",
    "", None, 123, ["https://dev.4impact.cc/"],
    "https://dev.4impact.cc/" + "a" * 3000,     # 過長
])
def test_unsafe_urls_rejected(url):
    assert issuers.safe_return(ISSUER_ID, url, "x") is None


def test_wildcard_does_not_match_bare_domain_unless_listed():
    assert issuers.safe_return(ISSUER_ID, "https://sechome.cc/", "x") is None           # beta 只登記 *.sechome.cc
    assert issuers.safe_return("tplanet-cms-stable", "https://sechome.cc/", "x") is not None


def test_unknown_issuer_or_no_return_hosts_gives_none():
    assert issuers.safe_return("someone-else", "https://dev.4impact.cc/", "x") is None
    with patch.dict(issuers.ISSUERS, {"bare": {"project": "p"}}):
        assert issuers.safe_return("bare", "https://dev.4impact.cc/", "x") is None


def test_label_is_plain_text_and_short():
    got = issuers.safe_return(ISSUER_ID, "https://dev.4impact.cc/", '<b>站名</b>"\n' + "長" * 60)
    assert "<" not in got["label"] and ">" not in got["label"] and '"' not in got["label"]
    assert "\n" not in got["label"] and len(got["label"]) <= 40
    assert issuers.safe_return(ISSUER_ID, "https://dev.4impact.cc/x", None)["label"] == "dev.4impact.cc"


# ── 通行證 → identity → cookie ──────────────────────────────────────
def test_verify_handoff_carries_return():
    idn = issuers.verify_handoff(_token(return_url="https://nantou-gov.sechome.cc/", return_label="南投"))
    assert idn["return"] == {"url": "https://nantou-gov.sechome.cc/", "label": "南投"}
    assert issuers.verify_handoff(_token())["return"] is None
    assert issuers.verify_handoff(_token(return_url="https://evil.example.com/"))["return"] is None


class _FakeConn:
    async def execute(self, *a):
        return "OK"

    async def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    mod = importlib.import_module("app.surfaces.sso")
    monkeypatch.setenv("CHAINLIT_AUTH_SECRET", "test-secret-172-" + "x" * 32)

    async def _connect():
        return _FakeConn()

    from fastapi.testclient import TestClient
    with patch.object(mod, "_DATABASE_URL", "postgresql://fake/db"), \
         patch.object(mod, "_connect", _connect), \
         patch.object(mod.issuers, "fetch_manifest", return_value={"tools": []}):
        yield TestClient(mod.fastapi_app)


def _cookie(resp, name):
    for h in resp.headers.get_list("set-cookie"):
        if h.startswith(name + "="):
            return h
    return None


def test_handoff_sets_return_cookie(client):
    resp = client.get("/sso/handoff", params={"token": _token(
        return_url="https://nantou-gov.sechome.cc/backend/cms_agent", return_label="南投縣計畫數位管理系統")},
        follow_redirects=False)
    assert resp.status_code == 303
    raw = _cookie(resp, "eva_return")
    assert raw and "Max-Age" in raw
    value = unquote(re.match(r"eva_return=([^;]*)", raw).group(1))
    if value.startswith('"'):
        value = json.loads(value)
    assert json.loads(value) == {"url": "https://nantou-gov.sechome.cc/backend/cms_agent",
                                 "label": "南投縣計畫數位管理系統"}


@pytest.mark.parametrize("extra", [{}, {"return_url": "https://evil.example.com/"}])
def test_handoff_without_valid_return_clears_cookie(client, extra):
    resp = client.get("/sso/handoff", params={"token": _token(**extra)}, follow_redirects=False)
    assert resp.status_code == 303
    raw = _cookie(resp, "eva_return")
    assert raw is not None and ("Max-Age=0" in raw or "expires=Thu, 01 Jan 1970" in raw.lower() or 'eva_return=""' in raw)


def test_custom_js_only_shows_button_with_cookie():
    js = open("public/custom.js", encoding="utf-8").read()
    block = js[js.index("ai-eva#172"):]
    assert "eva_return" in block and "if (!ret) return;" in block
    assert "/^https:\\/\\//" in block           # 前端再擋一次非 https
    assert "innerHTML" not in block             # 只用 textContent，不插 HTML
