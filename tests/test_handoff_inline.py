"""#246：帶 eva_sso_hint cookie 請求 / 時，<body> 之前就有同步內聯 script 掛 html.eva-handoff。"""
import os
import re

os.environ.setdefault("CHAINLIT_AUTH_SECRET", "test-246-" + "x" * 40)

from fastapi.testclient import TestClient  # noqa: E402

from app.surfaces import sso  # noqa: E402,F401  # 註冊 /sso/handoff 與 SPA 過場注入
from chainlit.server import app as fastapi_app  # noqa: E402

client = TestClient(fastapi_app)


def _before_body(html: str) -> str:
    i = html.lower().find("<body")
    assert i > 0, html[:500]
    return html[:i]


def _sync_inline_scripts(head: str) -> list[str]:
    out = []
    for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", head, re.S | re.I):
        if re.search(r"\b(src|async|defer|type\s*=\s*[\"']module)", attrs, re.I):
            continue
        out.append(body)
    return out


def _handoff_scripts(html: str) -> list[str]:
    return [s for s in _sync_inline_scripts(_before_body(html)) if "eva-handoff" in s]


def test_sso_hint_cookie_gets_sync_inline_handoff_before_body():
    r = client.get("/", cookies={"eva_sso_hint": "1"})
    assert r.status_code == 200
    scripts = _handoff_scripts(r.text)
    assert len(scripts) == 1, r.text[:2000]
    js = scripts[0]
    assert "eva_sso_hint" in js and 'classList.add("eva-handoff")' in js
    # 在任何外部 script 之前（不等外部檔案）
    head = _before_body(r.text)
    assert head.find("eva-handoff-inline") < head.find("<script src=") or "<script src=" not in head


def test_no_cookie_no_inline_handoff():
    r = client.get("/")
    assert r.status_code == 200
    assert "eva-handoff-inline" not in r.text
    assert not _handoff_scripts(r.text)


def test_other_spa_paths_also_covered():
    r = client.get("/thread/abc", cookies={"eva_sso_hint": "1"})
    assert r.status_code == 200 and len(_handoff_scripts(r.text)) == 1


def test_public_and_handoff_routes_not_shadowed():
    r = client.get("/public/custom.css", cookies={"eva_sso_hint": "1"})
    assert r.status_code == 200 and "eva-handoff-inline" not in r.text
    from chainlit import server as cl_server
    assert getattr(fastapi_app.router.routes[0], "path", None) == "/sso/handoff"
    spa = [r for r in cl_server.router.routes if getattr(r, "path", "").endswith("{full_path:path}")]
    assert len(spa) == 2 and spa[-1].endpoint is cl_server.serve
    r = client.get("/project/settings?language=en-US", cookies={"eva_sso_hint": "1"})
    assert "eva-handoff-inline" not in r.text


def test_inject_handles_head_with_attributes():
    out = sso.inject_handoff_inline('<html><head lang="x"><title>t</title></head><body></body></html>')
    assert out.startswith('<html><head lang="x"><script id="eva-handoff-inline">')
