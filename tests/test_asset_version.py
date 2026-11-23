"""#240：工作區腳本的版本參數＝檔案內容雜湊，部署後 CDN 不會再給舊檔。"""
import hashlib
import importlib
import re
import shutil
from urllib.parse import parse_qs, urlparse

import pytest

from app import assets_version
from app.apps.match_analysis import embed_route

HARDCODED = ("v=live-match", "v=law-task-2", "v=20261123return")
BODY = "<!doctype html><html><body><div id=app></div></body></html>"


def _h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def _srcs(html):
    return re.findall(r'<script src="([^"]+)"', html)


def _v(srcs, name):
    (src,) = [s for s in srcs if name in s]
    return parse_qs(urlparse(src).query)["v"][0]


@pytest.fixture
def copies(tmp_path, monkeypatch):
    task = tmp_path / "match-task.js"
    cards = tmp_path / "match-cards.js"
    shutil.copy(embed_route.TASK_JS, task)
    shutil.copy(embed_route.CARDS_JS, cards)
    monkeypatch.setattr(embed_route, "TASK_JS", task)
    monkeypatch.setattr(embed_route, "CARDS_JS", cards)
    embed_route.refresh()
    yield task, cards
    monkeypatch.undo()
    embed_route.refresh()


def test_inject_uses_real_file_hashes():
    srcs = _srcs(embed_route.inject(BODY))
    assert _v(srcs, "match-task.js") == _h(embed_route.TASK_JS)
    assert _v(srcs, "match-cards.js") == _h(embed_route.CARDS_JS)


def test_inject_version_follows_content(copies):
    task, cards = copies
    before = _srcs(embed_route.inject(BODY))
    assert _v(before, "match-task.js") == _h(task)
    assert _v(before, "match-cards.js") == _h(cards)
    for f in (task, cards):
        data = f.read_bytes()
        f.write_bytes(data[:-1] + (b"X" if data[-1:] != b"X" else b"Y"))
    embed_route.refresh()
    after = _srcs(embed_route.inject(BODY))
    for name, f in (("match-task.js", task), ("match-cards.js", cards)):
        assert _v(after, name) == _h(f)
        assert _v(after, name) != _v(before, name)


def test_custom_js_has_content_hashes(monkeypatch):
    monkeypatch.setenv("TANGLE_LAW_TASK", "1")
    monkeypatch.delenv("TANGLE_LAB", raising=False)
    from chainlit.config import config as chainlit_config
    old = chainlit_config.ui.custom_js
    try:
        import app.main as main
        importlib.reload(main)
        url = chainlit_config.ui.custom_js
    finally:
        chainlit_config.ui.custom_js = old
    q = parse_qs(urlparse(url).query)
    assert urlparse(url).path == "/public/tangle-lab-overlay.js"
    assert q["v"][0] == _h(assets_version.PUBLIC / "tangle-lab-overlay.js")
    assert q["c"][0] == _h(assets_version.PUBLIC / "custom.js")
    assert url == assets_version.custom_js_url()


def test_custom_js_hash_follows_content(tmp_path):
    f = tmp_path / "a.js"
    f.write_text("x")
    a = assets_version.content_hash(f)
    f.write_text("y")
    assert assets_version.content_hash(f) != a
    assert len(a) == 10


def test_no_hardcoded_versions():
    urls = _srcs(embed_route.inject(BODY)) + [assets_version.custom_js_url()]
    for url in urls:
        for bad in HARDCODED:
            assert bad not in url, url


def test_overlay_loads_custom_js_by_hash_param():
    overlay = (assets_version.PUBLIC / "tangle-lab-overlay.js").read_text(encoding="utf-8")
    head = overlay.split("\n", 5)
    assert any('searchParams.get("c")' in line and "custom.js?v=" in line for line in head)
